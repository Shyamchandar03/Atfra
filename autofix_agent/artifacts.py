from __future__ import annotations

import io
import zipfile


def _dom_snippet(html: str, selector_hint: str | None, max_chars: int = 12000) -> str:
    if not html:
        return ""
    if not selector_hint:
        return html[:max_chars]

    hint = selector_hint.strip()
    if (hint.startswith('"') and hint.endswith('"')) or (hint.startswith("'") and hint.endswith("'")):
        hint = hint[1:-1]

    candidates: list[str] = []
    if hint.startswith("#") and len(hint) > 1:
        candidates.append(f'id="{hint[1:]}"')
        candidates.append(f"id='{hint[1:]}'")
    if hint.startswith(".") and len(hint) > 1:
        # class matching is weaker; still helps.
        candidates.append(hint[1:])
    candidates.append(hint)

    for c in candidates:
        idx = html.find(c)
        if idx != -1:
            start = max(0, idx - 4000)
            end = min(len(html), idx + 8000)
            return html[start:end]

    return html[:max_chars]


def extract_playwright_artifact_context(
    zip_bytes: bytes, *, selector_hint: str | None = None
) -> dict:
    """
    Reads `artifacts/` zip from GitHub Actions and returns compact context for the LLM.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]

        html_name = next((n for n in names if n.lower().endswith(".html")), None)
        png_name = next((n for n in names if n.lower().endswith(".png")), None)
        trace_name = next((n for n in names if n.lower().endswith("-trace.zip")), None)

        dom_snippet = ""
        if html_name:
            with zf.open(html_name) as f:
                html = f.read().decode("utf-8", errors="replace")
            dom_snippet = _dom_snippet(html, selector_hint)

    return {
        "artifact_files": names[:200],
        "dom_html_file": html_name,
        "dom_snippet": dom_snippet,
        "screenshot_file": png_name,
        "trace_file": trace_name,
        "selector_hint": selector_hint,
    }

