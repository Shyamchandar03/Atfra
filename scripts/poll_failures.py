from __future__ import annotations

import time

from dotenv import load_dotenv

from autofix_agent.config import AgentConfig
from autofix_agent.github import GitHubClient


def main() -> int:
    """
    Polls GitHub Actions runs and prints failures.
    This is a lightweight alternative to a webhook listener; for full autonomous fixing,
    prefer the GitHub Actions `workflow_run` integration in `.github/workflows/autofix-agent.yml`.
    """
    load_dotenv(override=False)
    cfg = AgentConfig.from_env()
    gh = GitHubClient(token=cfg.github_token, repository=cfg.repository)

    workflow_id = gh.get_workflow_id(cfg.playwright_workflow_file)
    last_seen: int | None = None

    while True:
        data = gh._request(  # noqa: SLF001 - internal convenience
            "GET",
            f"/repos/{cfg.repository}/actions/workflows/{workflow_id}/runs",
            params={"per_page": 10},
        ).json()
        runs = data.get("workflow_runs", [])
        for run in runs:
            rid = int(run["id"])
            if last_seen is not None and rid <= last_seen:
                continue
            if run.get("conclusion") == "failure":
                print(f"Detected failing run: {rid} ({run.get('html_url')})")
            last_seen = max(last_seen or 0, rid)
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())

