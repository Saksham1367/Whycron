"""RQ task: dispatch alerts for one run.

Runs after the AI explainer finishes for failed pings, and after the
schedule scanner inserts a ``missed`` or ``timed_out`` row.
"""
from __future__ import annotations

import asyncio
import uuid

import structlog

log = structlog.get_logger("whycron.worker.notify")


def notify_run(run_id_str: str) -> dict[str, int]:
    run_id = uuid.UUID(run_id_str)
    log.info("notify_run_started", run_id=run_id_str)
    counts = asyncio.run(_notify_async(run_id))
    log.info("notify_run_finished", run_id=run_id_str, **counts)
    return counts


async def _notify_async(run_id: uuid.UUID) -> dict[str, int]:
    from apps.api.services.notify.dispatcher import notify_for_run

    return await notify_for_run(run_id)
