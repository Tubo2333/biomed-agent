# models.py — Pydantic request/response schemas for the REST API

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Request
# ═══════════════════════════════════════════════════════════════


class AnalysisRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Research question, e.g. 'CSTB in colorectal cancer prognosis'",
        examples=["CSTB 在结直肠癌中的预后价值和免疫浸润关联"],
    )


# ═══════════════════════════════════════════════════════════════
# Response
# ═══════════════════════════════════════════════════════════════


class TaskCreated(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatus(BaseModel):
    task_id: str
    question: str
    status: str  # pending | running | completed | failed
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    duration_ms: int | None = None
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    agent_results: list[dict[str, Any]] = []


class TaskReport(BaseModel):
    task_id: str
    question: str
    report: str | None = None
    status: str


class TaskList(BaseModel):
    tasks: list[dict[str, Any]]
    total: int


class StatsResponse(BaseModel):
    total_tasks: int
    completed: int
    failed: int
    avg_duration_ms: int
    total_tokens_input: int
    total_tokens_output: int


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
