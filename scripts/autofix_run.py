from __future__ import annotations

import os

from autofix_agent.orchestrator import run_from_github_event


def main() -> int:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        print("Missing GITHUB_EVENT_PATH.")
        return 2
    result = run_from_github_event(event_path)
    print(f"Autofix result: {result}")
    return 0 if result.outcome == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

