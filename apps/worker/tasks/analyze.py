"""RQ task: produce an AI explanation for a failed run.

This module is the entry point the worker dispatches to. RQ jobs are
synchronous functions; we wrap the async explainer in a fresh event loop
per job. Each job owns its own DB connection lifecycle to keep the worker
process stateless across jobs.
"""
from __future__ import annotations

import asyncio
import uuid

import structlog

log = structlog.get_logger("whycron.worker.analyze")


def analyze_run(run_id_str: str) -> str | None:
    """Sync RQ entry point. Returns the resulting ``AIExplanation.id``
    as a string, or ``None`` if the run was skipped."""
    run_id = uuid.UUID(run_id_str)
    log.info("analyze_run_started", run_id=run_id_str)
    explanation_id = asyncio.run(_analyze_async(run_id))
    log.info(
        "analyze_run_finished",
        run_id=run_id_str,
        explanation_id=str(explanation_id) if explanation_id else None,
    )
    return str(explanation_id) if explanation_id else None


async def _analyze_async(run_id: uuid.UUID) -> uuid.UUID | None:
    from apps.api.db import db
    from apps.api.services.ai_explainer import explain_failure

    await db.connect()
    try:
        return await explain_failure(run_id)
    finally:
        await db.disconnect()
