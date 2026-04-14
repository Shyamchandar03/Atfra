from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class FixRecord:
    run_id: int
    created_at: str
    category: str
    confidence: float
    summary: str
    branch: str | None
    pr_url: str | None
    outcome: str | None


class MemoryStore:
    def __init__(self, path: str = ".autofix/memory.sqlite"):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS fixes (
                  run_id INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  category TEXT NOT NULL,
                  confidence REAL NOT NULL,
                  summary TEXT NOT NULL,
                  branch TEXT,
                  pr_url TEXT,
                  outcome TEXT,
                  PRIMARY KEY (run_id, created_at)
                )
                """
            )

    def add(self, record: FixRecord) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO fixes (run_id, created_at, category, confidence, summary, branch, pr_url, outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.created_at,
                    record.category,
                    record.confidence,
                    record.summary,
                    record.branch,
                    record.pr_url,
                    record.outcome,
                ),
            )

    def list_recent(self, limit: int = 200) -> list[FixRecord]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT run_id, created_at, category, confidence, summary, branch, pr_url, outcome
                FROM fixes ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            FixRecord(
                run_id=int(r[0]),
                created_at=str(r[1]),
                category=str(r[2]),
                confidence=float(r[3]),
                summary=str(r[4]),
                branch=r[5],
                pr_url=r[6],
                outcome=r[7],
            )
            for r in rows
        ]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

