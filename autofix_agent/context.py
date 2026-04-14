from __future__ import annotations

import os
from dataclasses import dataclass

from .logs import ParsedFailure


@dataclass(frozen=True)
class CodeContext:
    files: dict[str, dict]


def _read_snippet(path: str, line: int | None, radius: int = 30) -> dict:
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return {"path": path, "exists": False}

    if not line or line < 1:
        start = 0
        end = min(len(lines), 120)
    else:
        start = max(0, line - 1 - radius)
        end = min(len(lines), line - 1 + radius)
    snippet = "\n".join(lines[start:end])
    return {"path": path, "exists": True, "line": line, "snippet": snippet}


def gather_code_context(failure: ParsedFailure) -> CodeContext:
    files: dict[str, dict] = {}
    if failure.failed_file:
        files[failure.failed_file] = _read_snippet(failure.failed_file, failure.failed_line)
    return CodeContext(files=files)

