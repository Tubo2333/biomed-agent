# logger.py — JSON Lines structured logging
#
# Usage:
#   from src.utils.logger import AgentLogger, get_logger
#   logger = AgentLogger("LiteratureAgent")
#   logger.agent_start(question="CSTB in CRC")
#   logger.agent_end(duration_ms=162460, tokens_used={"input": 500, "output": 300}, status="ok")

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════
# File setup
# ═══════════════════════════════════════════════════════════════

_LOG_DIR: Path | None = None
_LOG_LEVEL: str = "INFO"
_MAX_DAYS: int = 30
_init_lock = threading.Lock()


def init_logging(log_dir: str = "logs", level: str = "INFO", max_days: int = 30) -> None:
    """Initialize the logging subsystem.

    Called once at app startup. Creates the log directory and sets
    global log level. Automatically cleans logs older than max_days.

    Args:
        log_dir: Directory for JSON Lines log files.
        level: Python log level name.
        max_days: Auto-delete log files older than this many days.
    """
    global _LOG_DIR, _LOG_LEVEL, _MAX_DAYS
    with _init_lock:
        _LOG_DIR = Path(log_dir)
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _LOG_LEVEL = level.upper()
        _MAX_DAYS = max_days
        _purge_old_logs()


def _purge_old_logs() -> None:
    """Remove log files older than _MAX_DAYS."""
    if _LOG_DIR is None or not _LOG_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=_MAX_DAYS)
    for f in _LOG_DIR.glob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════
# AgentLogger
# ═══════════════════════════════════════════════════════════════


class AgentLogger:
    """Per-agent structured logger — writes JSON Lines to logs/<agent_name>.jsonl.

    Each line is a self-contained JSON object with timestamp, agent_name,
    event type, and event-specific fields.
    """

    def __init__(self, agent_name: str):
        self._agent = agent_name
        self._start_time: float | None = None
        # Also wire to Python stdlib logging for console output
        self._py_logger = logging.getLogger(f"biomed.{agent_name}")

    # ── File I/O ──────────────────────────────────────────

    def _write(self, event: str, **fields: Any) -> None:
        """Write a single JSON line to the log file."""
        if _LOG_DIR is None:
            init_logging()

        record: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "agent_name": self._agent,
            "event": event,
            **{k: v for k, v in fields.items() if v is not None},
        }

        # Write to JSON Lines file
        try:
            log_path = _LOG_DIR / f"{self._agent.lower()}.jsonl"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass  # Don't crash the app because of logging

        # Also emit to stdlib logger at appropriate level
        level = "ERROR" if event.startswith("error") else "INFO"
        if event.endswith("_start") or event == "cache_hit" or event == "cache_miss":
            level = "DEBUG"
        getattr(self._py_logger, level.lower())(
            "%s | %s", event, json.dumps({k: v for k, v in fields.items() if k != "tokens_used"})
        )

    # ── Agent lifecycle ───────────────────────────────────

    def agent_start(self, **context: Any) -> None:
        """Log agent execution start."""
        self._start_time = time.perf_counter()
        self._write("agent_start", **context)

    def agent_end(
        self,
        status: str = "ok",
        tokens_used: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        """Log agent execution end with duration and outcome."""
        duration_ms = 0
        if self._start_time is not None:
            duration_ms = int((time.perf_counter() - self._start_time) * 1000)
        self._write(
            "agent_end",
            status=status,
            duration_ms=duration_ms,
            tokens_used=tokens_used or {},
            error=error,
        )

    # ── Structured events ─────────────────────────────────

    def cache_hit(self, key: str, size_bytes: int = 0) -> None:
        self._write("cache_hit", key=key, size_bytes=size_bytes)

    def cache_miss(self, key: str) -> None:
        self._write("cache_miss", key=key)

    def llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
    ) -> None:
        self._write(
            "llm_call",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

    def validation_warning(self, check: str, detail: str) -> None:
        self._write("validation_warning", check=check, detail=detail)

    def error(self, error_type: str, detail: str) -> None:
        self._write("error", error_type=error_type, detail=detail)


# ═══════════════════════════════════════════════════════════════
# Convenience factory
# ═══════════════════════════════════════════════════════════════

_loggers: dict[str, AgentLogger] = {}


def get_logger(agent_name: str) -> AgentLogger:
    """Get or create an AgentLogger for the given agent name."""
    if agent_name not in _loggers:
        _loggers[agent_name] = AgentLogger(agent_name)
    return _loggers[agent_name]
