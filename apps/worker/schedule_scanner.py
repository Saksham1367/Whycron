"""Schedule evaluator — the missed-and-stuck detector.

Runs periodically inside the worker process via APScheduler. One pass over
every active monitor does three things:

1. **Missed detection** — for cron monitors, generates the expected fire
   times since the last recorded ping (or since the monitor was created)
   using ``croniter`` in the monitor's stored timezone. For each fire
   time that has elapsed past ``grace_period_seconds`` without a matching
   ping, inserts a synthetic ``state='missed'`` ``Run`` row.

2. **Stuck detection** — for any ``state='started'`` ``Run`` older than
   ``2 × expected_runtime_seconds`` that has no later terminal event,
   inserts a ``state='timed_out'`` ``Run`` capturing the elapsed duration.

3. **Status update** — sets ``monitor.status`` to the category implied by
   the latest terminal event (``succeeded → healthy``, ``failed/missed/
   timed_out → failing``, ``late → late``, ``paused → paused``, no events
   → ``unknown``).

The scan is idempotent: re-running it without any new pings is a no-op
because the missed-check looks for any ``started_at`` within ±grace of the
expected fire time.

Self-contained DB lifecycle: each call creates its own engine so the
function is safe to call from any thread/loop (APScheduler's loop, an
RQ job, a test). Tests inject ``session`` directly to skip the engine
creation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from croniter import croniter
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from apps.api.config import settings
from apps.api.db import _async_url
from apps.api.models import Monitor, Run

log = structlog.get_logger("whycron.scanner")

# How far back to look when a monitor has never had a ping.
_LOOKBACK_FOR_NEW_MONITOR = timedelta(days=7)
# Maximum missed rows we'll insert per monitor per scan — avoids runaway
# inserts if a monitor's been silent for weeks.
_MAX_MISSED_PER_SCAN_PER_MONITOR = 20
# Buffer multiplier for stuck detection: 2 × expected_runtime_seconds.
_STUCK_BUFFER_MULTIPLIER = 2
# Don't bother re-evaluating started runs older than this — they've been
# either already timed-out or are forgotten.
_STUCK_LOOKBACK = timedelta(days=7)

_TERMINAL_STATES = ("succeeded", "failed", "missed", "timed_out", "late")


async def scan_schedules(
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> dict[str, int]:
    """One pass. Returns counts ``{missed, timed_out, status_updates}``.

    Production callers pass ``now=None`` (uses wall-clock UTC). Tests inject
    a fixed ``now`` for deterministic assertions.
    """
    effective_now = now or datetime.now(timezone.utc)
    if session is not None:
        return await _scan_inner(session, effective_now)
    # Self-contained engine — see module docstring.
    engine = create_async_engine(_async_url(settings.database_url))
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            return await _scan_inner(s, effective_now)
    finally:
        await engine.dispose()


async def _scan_inner(session: AsyncSession, now: datetime) -> dict[str, int]:
    log.info("scan_started", now=now.isoformat())
    counts = {"missed": 0, "timed_out": 0, "status_updates": 0}

    monitors = (
        await session.execute(
            select(Monitor).where(Monitor.deleted_at.is_(None))
        )
    ).scalars().all()

    for monitor in monitors:
        if monitor.paused:
            if await _set_status_if_changed(session, monitor, "paused"):
                counts["status_updates"] += 1
            continue

        if monitor.schedule_type == "cron":
            counts["missed"] += await _check_missed_runs(session, monitor, now)

        counts["timed_out"] += await _check_stuck_runs(session, monitor, now)

        new_status = await _compute_status(session, monitor.id)
        if await _set_status_if_changed(session, monitor, new_status):
            counts["status_updates"] += 1

    await session.commit()
    log.info("scan_finished", **counts)
    return counts


# ── Missed-run detection ─────────────────────────────────────────────────────


async def _check_missed_runs(
    session: AsyncSession, monitor: Monitor, now: datetime
) -> int:
    grace = timedelta(seconds=monitor.grace_period_seconds)

    # Anchor on monitor.created_at, capped at the lookback window. We do
    # NOT anchor on the most recent ping — that would silently skip any
    # earlier missed fires that haven't been recorded yet. The per-fire
    # existence check below makes this safe and idempotent.
    earliest = now - _LOOKBACK_FOR_NEW_MONITOR
    if monitor.created_at is not None:
        anchor = max(monitor.created_at, earliest)
    else:
        anchor = earliest

    try:
        tz = ZoneInfo(monitor.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    try:
        iterator = croniter(monitor.schedule_value, anchor.astimezone(tz))
    except Exception as exc:
        log.warning(
            "invalid_cron",
            monitor_id=str(monitor.id),
            schedule=monitor.schedule_value,
            error=str(exc),
        )
        return 0

    inserted = 0
    while inserted < _MAX_MISSED_PER_SCAN_PER_MONITOR:
        next_fire_local = iterator.get_next(datetime)
        if next_fire_local.tzinfo is None:
            next_fire_utc = next_fire_local.replace(tzinfo=tz).astimezone(
                timezone.utc
            )
        else:
            next_fire_utc = next_fire_local.astimezone(timezone.utc)

        if next_fire_utc + grace > now:
            break

        # Any Run with started_at within ±grace counts as "this fire was
        # serviced" — covers a ping that arrived a little late as well as a
        # previously-inserted missed marker.
        existing = (
            await session.execute(
                select(Run.id)
                .where(
                    Run.monitor_id == monitor.id,
                    Run.started_at >= next_fire_utc - grace,
                    Run.started_at <= next_fire_utc + grace,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is None:
            missed_run = Run(
                organization_id=monitor.organization_id,
                monitor_id=monitor.id,
                state="missed",
                started_at=next_fire_utc,
            )
            session.add(missed_run)
            await session.flush()
            _enqueue_notify_safe(missed_run.id)
            inserted += 1

    return inserted


# ── Stuck-run detection ──────────────────────────────────────────────────────


async def _check_stuck_runs(
    session: AsyncSession, monitor: Monitor, now: datetime
) -> int:
    if monitor.expected_runtime_seconds is None:
        return 0

    threshold_seconds = (
        monitor.expected_runtime_seconds * _STUCK_BUFFER_MULTIPLIER
    )
    cutoff = now - timedelta(seconds=threshold_seconds)
    oldest = now - _STUCK_LOOKBACK

    stuck = (
        await session.execute(
            select(Run).where(
                Run.monitor_id == monitor.id,
                Run.state == "started",
                Run.ended_at.is_(None),
                Run.started_at.is_not(None),
                Run.started_at < cutoff,
                Run.started_at >= oldest,
            )
        )
    ).scalars().all()

    inserted = 0
    for run in stuck:
        if run.started_at is None:
            continue
        # If a later terminal event already exists for this monitor, the
        # started row is logically closed (success ping arrived, or we
        # inserted a timed_out on a previous scan).
        follow_up = (
            await session.execute(
                select(Run.id)
                .where(
                    Run.monitor_id == monitor.id,
                    Run.created_at > run.created_at,
                    Run.state.in_(_TERMINAL_STATES),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if follow_up is not None:
            continue

        elapsed_ms = int((now - run.started_at).total_seconds() * 1000)
        timed_out_run = Run(
            organization_id=monitor.organization_id,
            monitor_id=monitor.id,
            state="timed_out",
            started_at=run.started_at,
            ended_at=now,
            duration_ms=elapsed_ms,
        )
        session.add(timed_out_run)
        await session.flush()
        _enqueue_notify_safe(timed_out_run.id)
        inserted += 1

    return inserted


# ── Monitor status ───────────────────────────────────────────────────────────


async def _compute_status(
    session: AsyncSession, monitor_id: uuid.UUID
) -> str:
    # Order by effective event time, not row-insertion time. A retroactively
    # back-filled `missed` row has its `started_at` set to the expected fire
    # time in the past, but its `created_at` is "now" — ordering by
    # created_at would let yesterday's missed back-fill outrank today's
    # successful ping. Effective time = ended_at | started_at | created_at.
    effective_time = func.coalesce(
        Run.ended_at, Run.started_at, Run.created_at
    )
    latest = (
        await session.execute(
            select(Run.state)
            .where(
                Run.monitor_id == monitor_id,
                Run.state.in_(_TERMINAL_STATES),
            )
            .order_by(effective_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if latest is None:
        return "unknown"
    if latest == "succeeded":
        return "healthy"
    if latest == "late":
        return "late"
    return "failing"


def _enqueue_notify_safe(run_id: uuid.UUID) -> None:
    """Best-effort: enqueue a notify job. Failure must not break the scan."""
    try:
        from apps.api.services.queue import enqueue_notify_run

        enqueue_notify_run(run_id)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "notify_enqueue_failed", run_id=str(run_id), error=str(exc)
        )


async def _set_status_if_changed(
    session: AsyncSession, monitor: Monitor, new_status: str
) -> bool:
    if monitor.status == new_status:
        return False
    log.info(
        "monitor_status_changed",
        monitor_id=str(monitor.id),
        old=monitor.status,
        new=new_status,
    )
    await session.execute(
        update(Monitor)
        .where(Monitor.id == monitor.id)
        .values(status=new_status)
    )
    return True
