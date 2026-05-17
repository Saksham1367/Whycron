"""Whycron background worker — entry point.

This single process runs two things in parallel:

1. **APScheduler** (in a daemon thread, owns its own asyncio loop) fires
   ``scan_schedules`` every ``SCAN_INTERVAL_SECONDS`` to detect missed and
   stuck runs.

2. **RQ SimpleWorker** (main thread, blocking) consumes the ``analyze``
   queue and runs the AI explainer on failed pings.

Start with:

    uv run python -m apps.worker.main

In production, deploy as a single process (systemd unit, Docker service,
or a DigitalOcean app worker). Future phases may split these into separate
processes if scale demands.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

import sentry_sdk
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis import Redis
from rq import SimpleWorker
from sentry_sdk.integrations.threading import ThreadingIntegration

from apps.api.config import settings
from apps.worker.schedule_scanner import scan_schedules

ANALYZE_QUEUE = "analyze"
NOTIFY_QUEUE = "notify"
SCAN_INTERVAL_SECONDS = 30


def _configure_logging() -> None:
    level = getattr(logging, settings.log_level)
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _configure_sentry() -> None:
    """Initialize Sentry for the worker process. No-op when DSN absent
    (e.g., self-host without observability configured)."""
    if not settings.sentry_worker_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_worker_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=0.1,
        # The worker spawns the APScheduler in a thread; this integration
        # captures unhandled exceptions there too.
        integrations=[ThreadingIntegration(propagate_hub=True)],
        send_default_pii=False,
    )


def _run_scheduler_in_thread() -> None:
    """Run AsyncIOScheduler in its own thread with its own asyncio loop.

    APScheduler jobs are awaitable functions. We give them a dedicated loop
    so they don't collide with RQ workhorse loops in the main thread.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    scheduler = AsyncIOScheduler(event_loop=loop)
    scheduler.add_job(
        scan_schedules,
        "interval",
        seconds=SCAN_INTERVAL_SECONDS,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),  # run once at startup
        id="scan_schedules",
        replace_existing=True,
    )
    scheduler.start()
    try:
        loop.run_forever()
    finally:
        loop.close()


def main() -> None:
    _configure_logging()
    _configure_sentry()
    log = structlog.get_logger("whycron.worker")
    log.info(
        "worker_starting",
        queues=[ANALYZE_QUEUE, NOTIFY_QUEUE],
        scan_interval_seconds=SCAN_INTERVAL_SECONDS,
        sentry_enabled=bool(settings.sentry_worker_dsn),
    )

    threading.Thread(
        target=_run_scheduler_in_thread,
        daemon=True,
        name="apscheduler",
    ).start()

    redis_conn = Redis.from_url(settings.redis_url)
    # SimpleWorker runs jobs in-process (no os.fork) — required on Windows
    # and fine on Linux at V1+V2 volumes. See DECISIONS.md #18.
    worker = SimpleWorker(
        [ANALYZE_QUEUE, NOTIFY_QUEUE], connection=redis_conn
    )
    worker.work()


if __name__ == "__main__":
    main()
