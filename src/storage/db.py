# db.py — SQLite storage for analysis tasks and results
#
# Two tables:
#   tasks        — task metadata (input, status, timestamps)
#   task_results — per-agent outputs linked to a task

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════
# Connection management
# ═══════════════════════════════════════════════════════════════

_local = threading.local()


def _get_conn(db_path: str) -> sqlite3.Connection:
    """Get a thread-local database connection. Reconnects if path changed."""
    conn = getattr(_local, "conn", None)
    current_path = getattr(_local, "db_path", None)
    if conn is None or current_path != db_path:
        if conn is not None:
            conn.close()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(db_path)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.db_path = db_path
    return _local.conn


# ═══════════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════════

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id      TEXT PRIMARY KEY,
    question     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    -- status: pending | running | completed | failed
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    completed_at TEXT,
    error        TEXT,
    total_tokens_input  INTEGER DEFAULT 0,
    total_tokens_output INTEGER DEFAULT 0,
    duration_ms  INTEGER
);

CREATE TABLE IF NOT EXISTS task_results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    agent_name   TEXT NOT NULL,
    result_type  TEXT NOT NULL,
    -- result_type: literature_review | analysis_plan | analysis_result | report
    content_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_results_task_id ON task_results(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
"""


# ═══════════════════════════════════════════════════════════════
# TaskManager
# ═══════════════════════════════════════════════════════════════


class TaskManager:
    """High-level API for task CRUD and result storage."""

    def __init__(self, db_path: str = "data/biomed-agent.db"):
        self._db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        conn = _get_conn(self._db_path)
        conn.executescript(SCHEMA)
        conn.commit()

    # ── Task CRUD ──────────────────────────────────────────

    def create_task(self, question: str, task_id: str | None = None) -> str:
        """Create a new analysis task. Returns task_id."""
        import uuid

        tid = task_id or uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        conn = _get_conn(self._db_path)
        conn.execute(
            "INSERT INTO tasks (task_id, question, status, created_at) VALUES (?, ?, 'pending', ?)",
            (tid, question, now),
        )
        conn.commit()
        return tid

    def update_status(self, task_id: str, status: str, error: str | None = None) -> None:
        """Update task status (pending → running → completed/failed)."""
        now = datetime.now(timezone.utc).isoformat()
        conn = _get_conn(self._db_path)
        if status == "running":
            conn.execute(
                "UPDATE tasks SET status=?, started_at=? WHERE task_id=?",
                (status, now, task_id),
            )
        elif status in ("completed", "failed"):
            conn.execute(
                "UPDATE tasks SET status=?, completed_at=?, error=? WHERE task_id=?",
                (status, now, error, task_id),
            )
        else:
            conn.execute(
                "UPDATE tasks SET status=? WHERE task_id=?",
                (status, task_id),
            )
        conn.commit()

    def set_tokens(self, task_id: str, input_tokens: int, output_tokens: int, duration_ms: int) -> None:
        """Record token usage and duration for a completed task."""
        conn = _get_conn(self._db_path)
        conn.execute(
            "UPDATE tasks SET total_tokens_input=?, total_tokens_output=?, duration_ms=? WHERE task_id=?",
            (input_tokens, output_tokens, duration_ms, task_id),
        )
        conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Get task metadata as a dict, or None if not found."""
        conn = _get_conn(self._db_path)
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent tasks, newest first."""
        conn = _get_conn(self._db_path)
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Results ────────────────────────────────────────────

    def save_result(
        self,
        task_id: str,
        agent_name: str,
        result_type: str,
        content: dict[str, Any],
    ) -> None:
        """Save an agent's output for a task."""
        now = datetime.now(timezone.utc).isoformat()
        conn = _get_conn(self._db_path)
        conn.execute(
            "INSERT INTO task_results (task_id, agent_name, result_type, content_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, agent_name, result_type, json.dumps(content, ensure_ascii=False, default=str), now),
        )
        conn.commit()

    def get_results(self, task_id: str) -> list[dict[str, Any]]:
        """Get all agent results for a task, ordered by insertion."""
        conn = _get_conn(self._db_path)
        rows = conn.execute(
            "SELECT * FROM task_results WHERE task_id=? ORDER BY id",
            (task_id,),
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["content"] = json.loads(d.pop("content_json"))
            except json.JSONDecodeError:
                d["content"] = {}
            results.append(d)
        return results

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics across all tasks."""
        conn = _get_conn(self._db_path)
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='completed'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0]
        avg_duration = conn.execute(
            "SELECT AVG(duration_ms) FROM tasks WHERE duration_ms IS NOT NULL"
        ).fetchone()[0]
        total_tokens_in = conn.execute(
            "SELECT SUM(total_tokens_input) FROM tasks"
        ).fetchone()[0] or 0
        total_tokens_out = conn.execute(
            "SELECT SUM(total_tokens_output) FROM tasks"
        ).fetchone()[0] or 0
        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "avg_duration_ms": round(avg_duration) if avg_duration else 0,
            "total_tokens_input": total_tokens_in,
            "total_tokens_output": total_tokens_out,
        }
