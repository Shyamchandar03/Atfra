from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedFailure:
    raw_excerpt: str
    failed_test_nodeid: str | None
    failed_file: str | None
    failed_line: int | None
    exception_type: str | None
    exception_message: str | None


_NODEID_RE = re.compile(r"^(FAILED|ERROR)\s+([^\s]+)\s+-", re.MULTILINE)
_PYTEST_FILE_LINE_RE = re.compile(r"^(?P<file>[^:\n]+\.py):(?P<line>\d+):", re.MULTILINE)
_EXC_LINE_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*)(?::\s+(?P<msg>.*))?$", re.MULTILINE)


def extract_text_logs(zip_bytes: bytes, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    texts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(out_dir)
    for root, _, files in os.walk(out_dir):
        for fname in files:
            if not fname.lower().endswith((".txt", ".log")):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    texts.append(f.read())
            except OSError:
                continue
    return texts


def parse_first_failure(texts: list[str], max_excerpt_chars: int = 16000) -> ParsedFailure:
    joined = "\n\n".join(texts)
    # Prefer an excerpt centered on pytest failure markers, not just the tail (which is often installs).
    markers = [
        "============================= FAILURES =============================",
        "=========================== short test summary info ===========================",
        "Traceback (most recent call last):",
        "E   ",
        "\nFAILED ",
        "\nERROR ",
    ]
    idx = -1
    for m in markers:
        idx = joined.find(m)
        if idx != -1:
            break
    if idx == -1:
        excerpt = joined[-max_excerpt_chars:] if len(joined) > max_excerpt_chars else joined
    else:
        start = max(0, idx - 4000)
        end = min(len(joined), idx + max_excerpt_chars)
        excerpt = joined[start:end]

    nodeid_match = _NODEID_RE.search(joined)
    nodeid = nodeid_match.group(2) if nodeid_match else None

    file_line_match = _PYTEST_FILE_LINE_RE.search(joined)
    failed_file = file_line_match.group("file") if file_line_match else None
    failed_line = int(file_line_match.group("line")) if file_line_match else None

    exception_type = None
    exception_message = None
    # Extract exception from excerpt window first, then fall back to tail.
    search_windows = [excerpt, joined[-8000:]]
    for window in search_windows:
        for line in reversed(window.splitlines()):
            line = line.strip()
            if not line or line.startswith(("E   ", ">", "================", "FAILED", "ERROR")):
                continue
            m = _EXC_LINE_RE.match(line)
            if m and (m.group("type") or "").lower().endswith(("error", "exception", "assertionerror")):
                exception_type = m.group("type")
                exception_message = (m.group("msg") or "").strip() or None
                break
        if exception_type:
            break

    return ParsedFailure(
        raw_excerpt=excerpt,
        failed_test_nodeid=nodeid,
        failed_file=failed_file,
        failed_line=failed_line,
        exception_type=exception_type,
        exception_message=exception_message,
    )
