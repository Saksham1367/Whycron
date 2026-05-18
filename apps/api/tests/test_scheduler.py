"""Schedule evaluator tests.

These exercise the detection logic with controllable ``now`` and pre-seeded
monitor histories. The scanner under test lives in ``apps.worker.
schedule_scanner`` but is tested here so it can reuse the existing
``connected_db`` fixture.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update

from apps.api.db import db
from apps.api.models import AuditLog, Monitor, Organization, Run
from apps.worker.schedule_scanner import (
    _MAX_MISSED_PER_SCAN_PER_MONITOR,
    scan_schedules,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def fresh_monitor(
    connected_db: None,
) -> AsyncIterator[dict[str, Any]]:
    """Create an org + a cron monitor scheduled daily at 02:00 UTC."""
    test_id = uuid.uuid4().hex[:12]
    async with db.session() as s:
        org = Organization(
            name="Scheduler Test",
            slug=f"stest-{test_id}",
            tier="free",
        )
        s.add(org)
        await s.flush()
        monitor = Monitor(
            organization_id=org.id,
            name=f"Daily 2 AM {test_id}",
            ping_token=f"wcr_stest_{test_id}",
            schedule_type="cron",
            schedule_value="0 2 * * *",
            timezone="UTC",
            grace_period_seconds=60,
        )
        s.add(monitor)
        await s.commit()
        ctx = {"org_id": org.id, "monitor_id": monitor.id}

    yield ctx

    async with db.session() as s:
        await s.execute(
            delete(AuditLog).where(AuditLog.organization_id == ctx["org_id"])
        )
        # Delete every run for this monitor, not just runs whose org_id
        # matches — the scheduler can insert ``missed`` rows whose
        # organization_id is populated from the live monitor row but in
        # rare cases differs from what the test cached in ``ctx``. Deleting
        # by ``monitor_id`` guarantees we don't leave dangling FK pointers.
        await s.execute(delete(Run).where(Run.monitor_id == ctx["monitor_id"]))
        await s.execute(delete(Monitor).where(Monitor.id == ctx["monitor_id"]))
        await s.execute(
            delete(Organization).where(Organization.id == ctx["org_id"])
        )
        await s.commit()


async def _set_monitor_created_at(
    monitor_id: uuid.UUID, when: datetime
) -> None:
    async with db.session() as s:
        await s.execute(
            update(Monitor).where(Monitor.id == monitor_id).values(created_at=when)
        )
        await s.commit()


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_scan_returns_count_dict_with_expected_keys(
    connected_db: None,
) -> None:
    """Smoke test: scan_schedules always returns the documented counter
    shape regardless of what monitors exist. (We do not assert specific
    values because the dev DB may contain monitors from previous sessions.)"""
    counts = await scan_schedules(now=datetime.now(timezone.utc))
    assert set(counts.keys()) == {"missed", "timed_out", "status_updates"}
    for v in counts.values():
        assert isinstance(v, int)
        assert v >= 0


async def test_scan_inserts_missed_runs_for_silent_monitor(
    fresh_monitor: dict[str, Any],
) -> None:
    """Monitor created 2 days ago, schedule '0 2 * * *', no pings,
    now = today at 03:00 UTC. Expect 3 missed Runs (the two-days-ago,
    yesterday, today fires at 02:00 UTC)."""
    now = datetime(2026, 5, 11, 3, 0, 0, tzinfo=timezone.utc)
    await _set_monitor_created_at(
        fresh_monitor["monitor_id"], now - timedelta(days=2, hours=4)
    )

    counts = await scan_schedules(now=now)
    assert counts["missed"] == 3

    async with db.session() as s:
        runs = (
            await s.execute(
                select(Run)
                .where(Run.monitor_id == fresh_monitor["monitor_id"])
                .order_by(Run.started_at)
            )
        ).scalars().all()
    assert len(runs) == 3
    assert all(r.state == "missed" for r in runs)
    fire_hours = [r.started_at.hour for r in runs if r.started_at]
    assert fire_hours == [2, 2, 2]

    async with db.session() as s:
        monitor = (
            await s.execute(
                select(Monitor).where(Monitor.id == fresh_monitor["monitor_id"])
            )
        ).scalar_one()
    assert monitor.status == "failing"


async def test_scan_is_idempotent(fresh_monitor: dict[str, Any]) -> None:
    """Running the scan twice in a row produces no new rows the second time."""
    now = datetime(2026, 5, 11, 3, 0, 0, tzinfo=timezone.utc)
    await _set_monitor_created_at(
        fresh_monitor["monitor_id"], now - timedelta(days=2, hours=4)
    )

    first = await scan_schedules(now=now)
    second = await scan_schedules(now=now)
    assert first["missed"] == 3
    assert second["missed"] == 0

    async with db.session() as s:
        n = (
            await s.execute(
                select(Run).where(Run.monitor_id == fresh_monitor["monitor_id"])
            )
        ).scalars().all()
    assert len(n) == 3


async def test_scan_skips_paused_monitor(
    fresh_monitor: dict[str, Any],
) -> None:
    async with db.session() as s:
        await s.execute(
            update(Monitor)
            .where(Monitor.id == fresh_monitor["monitor_id"])
            .values(paused=True)
        )
        await s.commit()

    now = datetime(2026, 5, 11, 3, 0, 0, tzinfo=timezone.utc)
    await _set_monitor_created_at(
        fresh_monitor["monitor_id"], now - timedelta(days=2, hours=4)
    )

    counts = await scan_schedules(now=now)
    assert counts["missed"] == 0

    async with db.session() as s:
        runs = (
            await s.execute(
                select(Run).where(Run.monitor_id == fresh_monitor["monitor_id"])
            )
        ).scalars().all()
        monitor = (
            await s.execute(
                select(Monitor).where(Monitor.id == fresh_monitor["monitor_id"])
            )
        ).scalar_one()
    assert len(runs) == 0
    assert monitor.status == "paused"


async def test_scan_caps_missed_inserts_per_pass(
    fresh_monitor: dict[str, Any],
) -> None:
    """A monitor silent for years should not insert thousands of rows in
    a single scan. The cap is the safety valve."""
    now = datetime(2026, 5, 11, 3, 0, 0, tzinfo=timezone.utc)
    # Switch to every-5-minutes schedule and backdate created_at far enough
    # that an uncapped scan would produce thousands of fires.
    async with db.session() as s:
        await s.execute(
            update(Monitor)
            .where(Monitor.id == fresh_monitor["monitor_id"])
            .values(schedule_value="*/5 * * * *")
        )
        await s.commit()
    await _set_monitor_created_at(
        fresh_monitor["monitor_id"], now - timedelta(days=30)
    )

    counts = await scan_schedules(now=now)
    assert counts["missed"] == _MAX_MISSED_PER_SCAN_PER_MONITOR


async def test_scan_detects_stuck_run(fresh_monitor: dict[str, Any]) -> None:
    """A started Run older than 2× expected_runtime_seconds with no later
    terminal event must be flagged with a timed_out row."""
    now = datetime(2026, 5, 11, 3, 0, 0, tzinfo=timezone.utc)
    started_at = now - timedelta(minutes=30)

    async with db.session() as s:
        await s.execute(
            update(Monitor)
            .where(Monitor.id == fresh_monitor["monitor_id"])
            .values(expected_runtime_seconds=300)  # 5 minutes
        )
        s.add(
            Run(
                organization_id=fresh_monitor["org_id"],
                monitor_id=fresh_monitor["monitor_id"],
                state="started",
                started_at=started_at,
            )
        )
        await s.commit()

    # Park the monitor's created_at near `now` so missed detection is a no-op.
    await _set_monitor_created_at(
        fresh_monitor["monitor_id"], now - timedelta(hours=1)
    )

    counts = await scan_schedules(now=now)
    assert counts["timed_out"] == 1

    async with db.session() as s:
        timed_out = (
            await s.execute(
                select(Run).where(
                    Run.monitor_id == fresh_monitor["monitor_id"],
                    Run.state == "timed_out",
                )
            )
        ).scalar_one()
    assert timed_out.started_at == started_at
    assert timed_out.duration_ms is not None
    # ~30 minutes elapsed
    assert 25 * 60 * 1000 <= timed_out.duration_ms <= 35 * 60 * 1000

    # Second scan must NOT insert another timed_out — the existing terminal
    # row supersedes the stuck started.
    counts2 = await scan_schedules(now=now)
    assert counts2["timed_out"] == 0


async def test_scan_status_flips_to_healthy_after_success(
    fresh_monitor: dict[str, Any],
) -> None:
    """After a missed run drives status to failing, a successful run
    afterwards should flip status back to healthy on the next scan."""
    now = datetime(2026, 5, 11, 3, 0, 0, tzinfo=timezone.utc)
    await _set_monitor_created_at(
        fresh_monitor["monitor_id"], now - timedelta(days=1, hours=4)
    )

    await scan_schedules(now=now)
    async with db.session() as s:
        m = (
            await s.execute(
                select(Monitor).where(Monitor.id == fresh_monitor["monitor_id"])
            )
        ).scalar_one()
    assert m.status == "failing"

    # Simulate a successful ping arriving now.
    async with db.session() as s:
        s.add(
            Run(
                organization_id=fresh_monitor["org_id"],
                monitor_id=fresh_monitor["monitor_id"],
                state="succeeded",
                ended_at=now,
            )
        )
        await s.commit()

    counts = await scan_schedules(now=now + timedelta(seconds=1))
    assert counts["status_updates"] >= 1

    async with db.session() as s:
        m = (
            await s.execute(
                select(Monitor).where(Monitor.id == fresh_monitor["monitor_id"])
            )
        ).scalar_one()
    assert m.status == "healthy"


async def test_scan_invalid_cron_is_skipped_gracefully(
    fresh_monitor: dict[str, Any],
) -> None:
    """A monitor with a malformed cron expression should not crash the
    scan — it logs a warning and moves on. We assert only that *this*
    monitor produced no missed rows, since other monitors in the dev DB
    may legitimately produce some."""
    async with db.session() as s:
        await s.execute(
            update(Monitor)
            .where(Monitor.id == fresh_monitor["monitor_id"])
            .values(schedule_value="not a valid cron")
        )
        await s.commit()

    # Must not raise.
    await scan_schedules(now=datetime.now(timezone.utc))

    async with db.session() as s:
        runs = (
            await s.execute(
                select(Run).where(
                    Run.monitor_id == fresh_monitor["monitor_id"]
                )
            )
        ).scalars().all()
    assert all(r.state != "missed" for r in runs)


async def test_scan_recent_ping_skips_missed_for_that_window(
    fresh_monitor: dict[str, Any],
) -> None:
    """If a ping arrived within ±grace of an expected fire time, no
    missed row should be inserted for that fire."""
    now = datetime(2026, 5, 11, 3, 0, 0, tzinfo=timezone.utc)
    today_2am = datetime(2026, 5, 11, 2, 0, 0, tzinfo=timezone.utc)
    await _set_monitor_created_at(
        fresh_monitor["monitor_id"], now - timedelta(days=2, hours=4)
    )

    # Real ping arrived at exactly 02:00:30 today.
    async with db.session() as s:
        s.add(
            Run(
                organization_id=fresh_monitor["org_id"],
                monitor_id=fresh_monitor["monitor_id"],
                state="succeeded",
                started_at=today_2am + timedelta(seconds=30),
                ended_at=today_2am + timedelta(minutes=2),
            )
        )
        await s.commit()

    counts = await scan_schedules(now=now)
    # Two earlier fires were still missed; today's is covered by the ping.
    assert counts["missed"] == 2

    async with db.session() as s:
        missed_rows = (
            await s.execute(
                select(Run).where(
                    Run.monitor_id == fresh_monitor["monitor_id"],
                    Run.state == "missed",
                )
            )
        ).scalars().all()
    assert len(missed_rows) == 2
    # The most recent terminal event is a succeeded → status = healthy.
    async with db.session() as s:
        m = (
            await s.execute(
                select(Monitor).where(Monitor.id == fresh_monitor["monitor_id"])
            )
        ).scalar_one()
    assert m.status == "healthy"
