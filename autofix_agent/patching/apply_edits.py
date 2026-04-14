from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppliedEdit:
    file_path: str
    changed: bool
    reason: str


def apply_llm_edits(edits: list[dict], repo_root: str = ".") -> list[AppliedEdit]:
    results: list[AppliedEdit] = []
    root_norm = os.path.normpath(repo_root)
    for e in edits:
        file_path = e["file_path"]
        anchor = e["anchor"]
        replacement = e["replacement"]

        abs_path = os.path.normpath(os.path.join(repo_root, file_path))
        if not abs_path.startswith(root_norm):
            results.append(AppliedEdit(file_path, False, "Skipped: path traversal detected."))
            continue
        if not os.path.exists(abs_path):
            results.append(AppliedEdit(file_path, False, "Skipped: file not found."))
            continue

        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()

        if anchor not in original:
            results.append(AppliedEdit(file_path, False, "Skipped: anchor not found."))
            continue
        if original.count(anchor) != 1:
            results.append(AppliedEdit(file_path, False, "Skipped: anchor not unique."))
            continue

        updated = original.replace(anchor, replacement)
        if updated == original:
            results.append(AppliedEdit(file_path, False, "No-op replacement."))
            continue

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(updated)

        results.append(AppliedEdit(file_path, True, "Applied."))
    return results

