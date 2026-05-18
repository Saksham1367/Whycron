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
    from apps.api.config import settings

    run_id = uuid.UUID(run_id_str)
    log.info("analyze_run_started", run_id=run_id_str)

    # AI explanations are a SaaS-only differentiator (Phase 15). In
    # self-host mode (or anywhere ANTHROPIC_API_KEY isn't set) we still
    # enqueue notify so the user gets a plain alert — just without the
    # AI explanation block.
    if not settings.ai_enabled:
        log.info(
            "analyze_skipped_ai_disabled",
            run_id=run_id_str,
            self_host_mode=settings.self_host_mode,
        )
        asyncio.run(_enqueue_notify_async(run_id))
        return None

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


async def _enqueue_notify_async(run_id: uuid.UUID) -> None:
    """Self-host path: skip the LLM call but still trigger notification
    fan-out so the user gets the alert."""
    from apps.api.services.queue import enqueue_notify_run

    await asyncio.to_thread(enqueue_notify_run, run_id)
