from __future__ import annotations

import os

from autofix_agent.orchestrator import run_from_github_event


def main() -> int:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        print("Missing GITHUB_EVENT_PATH.")
        return 2
    try:
        result = run_from_github_event(event_path)
    except Exception as e:  # noqa: BLE001
        print(f"Autofix crashed: {e}")
        return 0
    print(f"Autofix result: {result}")
    # Don't fail the autofix workflow unless the agent itself crashes.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
