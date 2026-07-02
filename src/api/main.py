# main.py — FastAPI application entry point
#
# Usage:
#   python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
#   or: python src/api/main.py

from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.models import (
    AnalysisRequest,
    HealthResponse,
    StatsResponse,
    TaskCreated,
    TaskList,
    TaskReport,
    TaskStatus,
)
from src.config import config
from src.storage.db import TaskManager
from src.utils.logger import get_logger, init_logging


# ═══════════════════════════════════════════════════════════════
# App lifecycle
# ═══════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init logging, verify DB. Shutdown: cleanup."""
    # Startup
    init_logging(
        log_dir=config.logging.dir,
        level=config.logging.level,
        max_days=config.logging.max_days,
    )
    logging.getLogger("biomed.api").info(
        "BioMed-Agent API starting on %s:%s",
        config.api.host,
        config.api.port,
    )
    # Verify DB is ready
    TaskManager(config.storage.db_path)
    logging.getLogger("biomed.api").info(
        "Database ready at %s", config.storage.db_path,
    )
    yield
    # Shutdown
    logging.getLogger("biomed.api").info("BioMed-Agent API shutting down")


app = FastAPI(
    title="BioMed-Agent API",
    description="Multi-agent biomedical literature-grounded multi-omics analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _get_db() -> TaskManager:
    return TaskManager(config.storage.db_path)


async def _run_pipeline(task_id: str, question: str) -> None:
    """Background: execute the full 4-agent pipeline for a task."""
    db = _get_db()
    logger = get_logger("pipeline")

    try:
        db.update_status(task_id, "running")
        logger.agent_start(task_id=task_id, question=question)

        # Import here to avoid circular imports at module level
        from src.llm.client import LLMClient
        from src.agents.pipeline import MultiAgentPipeline

        llm_client = LLMClient(
            model=config.llm.model,
            temperature=config.llm.temperature,
        )

        if not llm_client.check_connectivity():
            raise RuntimeError("LLM API not reachable — check ANTHROPIC_AUTH_TOKEN and proxy settings")

        pipeline = MultiAgentPipeline(llm_client)
        result = pipeline.run(question)

        # Save each agent's output
        if hasattr(result, "literature_review"):
            db.save_result(task_id, "LiteratureAgent", "literature_review", {
                "papers_retrieved": getattr(result.literature_review, "papers_retrieved", 0),
                "hypotheses_count": len(getattr(result.literature_review, "hypotheses", [])),
                "confidence": getattr(result.literature_review, "confidence", 0),
            })
        if hasattr(result, "analysis_results"):
            for ar in result.analysis_results:
                db.save_result(task_id, "AnalysisAgent", "analysis_result", {
                    "node_id": getattr(ar, "node_id", ""),
                    "task": getattr(ar, "task", ""),
                    "status": getattr(ar, "status", ""),
                    "output": getattr(ar, "output", {}),
                })
        if hasattr(result, "report"):
            db.save_result(task_id, "ReportAgent", "report", {
                "report_text": getattr(result, "report", ""),
            })

        # Finalize
        tokens = getattr(result, "total_tokens", {"input": 0, "output": 0})
        db.set_tokens(task_id, tokens.get("input", 0), tokens.get("output", 0), 0)
        db.update_status(task_id, "completed")
        logger.agent_end(status="ok", tokens_used=tokens)

    except Exception as exc:
        error_detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        db.update_status(task_id, "failed", error=error_detail)
        logger.error(error_type=type(exc).__name__, detail=str(exc))


# ═══════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


@app.post("/analysis", response_model=TaskCreated, status_code=201)
async def create_analysis(req: AnalysisRequest):
    """Submit a new analysis task.

    Accepts a research question, creates a task record,
    and starts background execution of the 4-agent pipeline.
    Returns a task_id for status polling.
    """
    db = _get_db()
    task_id = db.create_task(req.question.strip())

    # Launch background execution
    asyncio.create_task(_run_pipeline(task_id, req.question.strip()))

    return TaskCreated(
        task_id=task_id,
        status="pending",
        message=f"Analysis task created. Poll GET /analysis/{task_id} for status.",
    )


@app.get("/analysis/{task_id}", response_model=TaskStatus)
async def get_analysis_status(task_id: str):
    """Get the current status and results of an analysis task."""
    db = _get_db()
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    agent_results = db.get_results(task_id)

    return TaskStatus(
        task_id=task["task_id"],
        question=task["question"],
        status=task["status"],
        created_at=task["created_at"],
        started_at=task.get("started_at"),
        completed_at=task.get("completed_at"),
        error=task.get("error"),
        duration_ms=task.get("duration_ms"),
        total_tokens_input=task.get("total_tokens_input", 0),
        total_tokens_output=task.get("total_tokens_output", 0),
        agent_results=agent_results,
    )


@app.get("/analysis/{task_id}/report", response_model=TaskReport)
async def get_analysis_report(task_id: str):
    """Get the full report for a completed analysis task."""
    db = _get_db()
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if task["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Task is {task['status']}, not completed. No report available yet.",
        )

    results = db.get_results(task_id)
    report_text = None
    for r in results:
        if r["result_type"] == "report" and r.get("content"):
            report_text = r["content"].get("report_text", "")

    return TaskReport(
        task_id=task_id,
        question=task["question"],
        report=report_text,
        status=task["status"],
    )


@app.get("/analysis", response_model=TaskList)
async def list_analyses(limit: int = 20):
    """List recent analysis tasks."""
    db = _get_db()
    tasks = db.list_tasks(limit=limit)
    return TaskList(tasks=tasks, total=len(tasks))


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get aggregate statistics across all tasks."""
    db = _get_db()
    stats = db.get_stats()
    return StatsResponse(**stats)


# ═══════════════════════════════════════════════════════════════
# Cache middleware
# ═══════════════════════════════════════════════════════════════


@app.middleware("http")
async def add_cache_header(request: Request, call_next):
    """Add X-Cache header based on whether the response came from cache."""
    response = await call_next(request)
    # Set by cache layer if the result was served from cache
    if not response.headers.get("X-Cache"):
        response.headers["X-Cache"] = "MISS"
    return response


# ═══════════════════════════════════════════════════════════════
# Direct run
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=True,
    )
