from __future__ import annotations

import argparse
import json
import sys

from autofix_agent.patching.apply_edits import apply_llm_edits


def main() -> int:
    p = argparse.ArgumentParser(description="Apply an autofix patch plan to the repo.")
    p.add_argument("--plan", required=True, help="Path to JSON fix plan (LlmFixPlan).")
    p.add_argument(
        "--playwright-expect-visible",
        action="append",
        default=[],
        help='Extra AST patch: <file>:<selector_literal>, e.g. tests/test.py:"\\"#submit\\""',
    )
    args = p.parse_args()

    with open(args.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)

    edits = plan.get("edits", [])
    results = apply_llm_edits(edits, repo_root=".")
    for r in results:
        print(f"{r.file_path}: {r.reason}")

    for item in args.playwright_expect_visible:
        try:
            from autofix_agent.patching.playwright_cst import (  # noqa: PLC0415
                insert_expect_visible_before_action,
            )
        except ModuleNotFoundError as e:
            print(
                "Missing optional dependency for AST patching. Install `requirements-agent.txt`.\n"
                f"Details: {e}"
            )
            return 3
        if ":" not in item:
            print(f"Invalid --playwright-expect-visible: {item}")
            return 2
        file_path, selector_literal = item.split(":", 1)
        with open(file_path, "r", encoding="utf-8") as f:
            src = f.read()
        patch = insert_expect_visible_before_action(src, selector_literal=selector_literal)
        if patch.changed and patch.updated_source is not None:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(patch.updated_source)
            print(f"{file_path}: {patch.reason}")
        else:
            print(f"{file_path}: skipped ({patch.reason})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
