from __future__ import annotations

import streamlit as st

from autofix_agent.memory import MemoryStore


st.set_page_config(page_title="Autofix Dashboard", layout="wide")
st.title("Autonomous Test Failure Resolution Agent")

store = MemoryStore()
rows = store.list_recent(limit=200)

st.metric("Fix records", len(rows))

if not rows:
    st.info("No fixes recorded yet. Run the autofix workflow on a failing CI run.")
    raise SystemExit(0)

st.dataframe(
    [
        {
            "run_id": r.run_id,
            "created_at": r.created_at,
            "category": r.category,
            "confidence": r.confidence,
            "summary": r.summary,
            "branch": r.branch,
            "pr_url": r.pr_url,
            "outcome": r.outcome,
        }
        for r in rows
    ],
    use_container_width=True,
)

