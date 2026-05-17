"""RQ enqueue helpers — sync RQ wrapped for async callers.

RQ uses a synchronous Redis client and pickle-based job serialization. The
ping handler is async, so it calls ``enqueue_analyze_run`` via
``asyncio.to_thread`` to avoid blocking the event loop.

Failures here are deliberately swallowed by the caller — the run is
already durably stored, and the schedule evaluator (Phase 4) will pick up
any failed runs whose analyze job didn't enqueue successfully.
"""
from __future__ import annotations

import uuid

from redis import Redis as SyncRedis
from rq import Queue

from apps.api.config import settings

ANALYZE_QUEUE = "analyze"
NOTIFY_QUEUE = "notify"


def _redis() -> SyncRedis:
    return SyncRedis.from_url(settings.redis_url)


def enqueue_analyze_run(run_id: uuid.UUID) -> str:
    """Push an analyze job onto the ``analyze`` queue. Returns the RQ
    job ID for diagnostic logging."""
    queue = Queue(ANALYZE_QUEUE, connection=_redis())
    job = queue.enqueue(
        "apps.worker.tasks.analyze.analyze_run",
        str(run_id),
    )
    return job.id


def enqueue_notify_run(run_id: uuid.UUID) -> str:
    """Push a notify job onto the ``notify`` queue."""
    queue = Queue(NOTIFY_QUEUE, connection=_redis())
    job = queue.enqueue(
        "apps.worker.tasks.notify.notify_run",
        str(run_id),
    )
    return job.id
