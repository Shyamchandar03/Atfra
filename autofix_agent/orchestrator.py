from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass

from dotenv import load_dotenv

from .config import AgentConfig
from .context import gather_code_context
from .failure import classify_failure
from .github import GitHubClient, GitHubError, WorkflowRunRef
from .llm.gemini import generate_json
from .llm.prompts import LlmFixPlan, PromptInputs, build_fix_prompt
from .logs import extract_text_logs, parse_failure_from_artifact_zip, parse_first_failure
from .memory import FixRecord, MemoryStore, utc_now_iso
from .notify import NoopNotifier, SlackNotifier
from .patching import apply_llm_edits


@dataclass(frozen=True)
class AutofixResult:
    run_id: int
    outcome: str
    branch: str | None = None
    pr_url: str | None = None
    summary: str | None = None


def _load_event(event_path: str) -> dict:
    with open(event_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _pick_notifier(cfg: AgentConfig):
    if cfg.slack_webhook_url:
        return SlackNotifier(cfg.slack_webhook_url)
    return NoopNotifier()


def run_from_github_event(event_path: str) -> AutofixResult:
    """
    Entrypoint for GitHub Actions `workflow_run` triggered workflows.
    Expects the repository to be checked out at `workflow_run.head_sha` for correct code context.
    """
    load_dotenv(override=False)
    cfg = AgentConfig.from_env()
    gh = GitHubClient(token=cfg.github_token, repository=cfg.repository)
    memory = MemoryStore()
    notifier = _pick_notifier(cfg)

    event = _load_event(event_path)
    workflow_run = event.get("workflow_run") or {}
    run_id = int(workflow_run.get("id") or 0)
    if not run_id:
        raise RuntimeError("Unsupported event payload: missing workflow_run.id")

    run_ref = gh.get_workflow_run(run_id)
    if run_ref.conclusion != "failure":
        return AutofixResult(run_id=run_id, outcome=f"skipped: conclusion={run_ref.conclusion}")

    notifier.send("Autofix started", f"{cfg.repository} run {run_id} failed; attempting repair.")

    # Optional flaky signal: rerun once without changes. If it passes, treat as flaky/infrastructure.
    if cfg.flaky_rerun_once:
        try:
            gh.rerun_workflow(run_id)
        except Exception:
            pass

    for attempt in range(1, cfg.max_attempts + 1):
        branch = f"autofix/run-{run_id}-a{attempt}"
        base_sha = run_ref.head_sha
        gh.create_or_reset_branch(branch, base_sha)

        with tempfile.TemporaryDirectory(prefix="autofix-logs-") as tmp:
            parsed = None
            try:
                zip_bytes = gh.download_workflow_logs_zip(run_id)
                texts = extract_text_logs(zip_bytes, os.path.join(tmp, "logs"))
                parsed = parse_first_failure(texts)
            except GitHubError as e:
                # Fallback: use junit artifact if log download is temporarily unavailable.
                if 500 <= e.status_code < 600:
                    artifacts = gh.list_run_artifacts(run_id)
                    junit = next((a for a in artifacts if a.get("name") == "pytest-results"), None)
                    if junit and not junit.get("expired", False):
                        zip_bytes = gh.download_artifact_zip(int(junit["id"]))
                        parsed = parse_failure_from_artifact_zip(zip_bytes)
            if parsed is None:
                memory.add(
                    FixRecord(
                        run_id=run_id,
                        created_at=utc_now_iso(),
                        category="unknown",
                        confidence=0.0,
                        summary="Unable to fetch logs/artifacts for failure analysis.",
                        branch=branch,
                        pr_url=None,
                        outcome="skipped_logs_unavailable",
                    )
                )
                return AutofixResult(run_id=run_id, outcome="skipped: logs unavailable", branch=branch)

            classification = classify_failure(parsed)
            context = gather_code_context(parsed)

        prompt = build_fix_prompt(
            PromptInputs(
                repo=cfg.repository,
                failure_excerpt=parsed.raw_excerpt,
                classification=asdict(classification),
                code_context={"files": context.files},
            )
        )

        fix_json = generate_json(
            api_key=cfg.gemini_api_key,
            model=cfg.gemini_model,
            prompt=prompt,
            temperature=0.2,
        )
        plan = LlmFixPlan.model_validate(fix_json)

        applied = apply_llm_edits([e.model_dump() for e in plan.edits], repo_root=".")
        changed_files = [a.file_path for a in applied if a.changed]
        if not changed_files:
            memory.add(
                FixRecord(
                    run_id=run_id,
                    created_at=utc_now_iso(),
                    category=plan.category,
                    confidence=float(plan.confidence),
                    summary=plan.summary,
                    branch=branch,
                    pr_url=None,
                    outcome="no_changes_applied",
                )
            )
            return AutofixResult(run_id=run_id, outcome="failed: no changes applied", branch=branch)

        files_payload: dict[str, str] = {}
        for path in changed_files:
            with open(path, "r", encoding="utf-8") as f:
                files_payload[path] = f.read()

        gh.commit_files_to_branch(
            branch=branch,
            message=f"Autofix attempt {attempt}: {plan.summary}",
            files=files_payload,
        )

        gh.dispatch_workflow(cfg.playwright_workflow_file, ref=branch)
        workflow_id = gh.get_workflow_id(cfg.playwright_workflow_file)

        dispatched_run: WorkflowRunRef | None = None
        for _ in range(30):
            dispatched_run = gh.find_latest_run_for_ref(workflow_id, ref=branch)
            if dispatched_run:
                break
            time.sleep(5)
        if not dispatched_run:
            raise RuntimeError("Dispatched workflow run not found for branch.")

        final = gh.wait_for_run_completion(dispatched_run.run_id, timeout_s=2400, poll_s=10)
        if final.conclusion == "success":
            pr_body = (
                f"Root cause (agent): {plan.summary}\n\n"
                f"Category: {plan.category}\n"
                f"Confidence: {plan.confidence:.2f}\n\n"
                "Applied edits:\n"
                + "\n".join(f"- `{a.file_path}`: {a.reason}" for a in applied)
                + "\n\n"
                f"Validation run: {gh.get_workflow_run_url(final.run_id)}\n"
                f"Original failing run: {gh.get_workflow_run_url(run_id)}\n"
            )
            pr_url = gh.create_pull_request(
                title=f"Autofix: {plan.summary}",
                body=pr_body,
                head=branch,
                base=cfg.default_branch,
                draft=False,
            )
            memory.add(
                FixRecord(
                    run_id=run_id,
                    created_at=utc_now_iso(),
                    category=plan.category,
                    confidence=float(plan.confidence),
                    summary=plan.summary,
                    branch=branch,
                    pr_url=pr_url,
                    outcome="pr_created",
                )
            )
            notifier.send("Autofix succeeded", f"PR created: {pr_url}")
            return AutofixResult(
                run_id=run_id,
                outcome="success",
                branch=branch,
                pr_url=pr_url,
                summary=plan.summary,
            )

        memory.add(
            FixRecord(
                run_id=run_id,
                created_at=utc_now_iso(),
                category=plan.category,
                confidence=float(plan.confidence),
                summary=plan.summary,
                branch=branch,
                pr_url=None,
                outcome=f"validation_failed:{final.run_id}",
            )
        )

    notifier.send("Autofix failed", f"Exhausted {cfg.max_attempts} attempts for run {run_id}.")
    return AutofixResult(run_id=run_id, outcome="failed: max attempts reached")
