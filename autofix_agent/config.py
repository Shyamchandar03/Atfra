from __future__ import annotations

from dataclasses import dataclass
import os


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AgentConfig:
    github_token: str
    github_pr_token: str | None
    repository: str  # owner/repo
    default_branch: str

    gemini_api_key: str
    gemini_model: str

    playwright_workflow_file: str

    max_attempts: int
    flaky_rerun_once: bool

    slack_webhook_url: str | None

    @staticmethod
    def from_env() -> "AgentConfig":
        github_token = _env("GITHUB_TOKEN") or _env("GH_TOKEN")
        if not github_token:
            raise RuntimeError("Missing GITHUB_TOKEN (or GH_TOKEN).")

        # Optional: use a separate token for PR creation (PAT / fine-grained token).
        # Useful when the repo setting "GitHub Actions is permitted to create or approve pull requests"
        # is disabled for the default GITHUB_TOKEN.
        github_pr_token = _env("GITHUB_PR_TOKEN")

        repository = _env("GITHUB_REPOSITORY")
        if not repository:
            raise RuntimeError("Missing GITHUB_REPOSITORY (owner/repo).")

        gemini_api_key = _env("GEMINI_API_KEY")
        if not gemini_api_key:
            raise RuntimeError("Missing GEMINI_API_KEY.")

        return AgentConfig(
            github_token=github_token,
            github_pr_token=github_pr_token,
            repository=repository,
            default_branch=_env("DEFAULT_BRANCH", "main") or "main",
            gemini_api_key=gemini_api_key,
            gemini_model=_env("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash",
            playwright_workflow_file=_env("PLAYWRIGHT_WORKFLOW_FILE", "playwright.yml")
            or "playwright.yml",
            max_attempts=_env_int("AUTOFIX_MAX_ATTEMPTS", 3),
            flaky_rerun_once=(_env("AUTOFIX_FLAKY_RERUN_ONCE", "false") or "false")
            .lower()
            .strip()
            in {"1", "true", "yes", "y"},
            slack_webhook_url=_env("SLACK_WEBHOOK_URL"),
        )
