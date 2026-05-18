"""Compute the public status-page snapshot for an organization.

The snapshot is a small JSON-serializable structure rendered to HTML by
``apps.api.routes.status``. It is cached in Redis for 60s, so a busy
public page only hits Postgres once per minute regardless of traffic.

Day buckets and the overall status are computed defensively — privacy
matters here. The public route must:

- Never include private (``is_public=false``) monitors
- Never include any free-text the user typed (log excerpts, monitor
  names that might contain customer data are still considered "fair
  game" because the user opted in by flagging the monitor public, but
  the route never echoes user-supplied URLs, configs, or AI explanation
  bodies)
- 404 fast — Redis lookup, single Postgres SELECT — when the slug is
  unknown so we don't leak whether a slug exists by timing.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import db
from apps.api.models import Monitor, Organization, Run
from apps.api.redis_client import redis_client

log = structlog.get_logger("whycron.status_page")

_CACHE_PREFIX = "status_page:"
_CACHE_TTL_SECONDS = 60
DAY_BUCKETS = 30


@dataclass(frozen=True)
class DayBucket:
    """One day's worst-state for a monitor. Used to render the dot row."""

    date: str  # ISO YYYY-MM-DD
    state: str  # 'no_data' | 'succeeded' | 'late' | 'failed' | 'missed' | 'timed_out'


@dataclass(frozen=True)
class PublicMonitor:
    name: str
    status: str
    schedule_value: str
    schedule_type: str
    days: list[DayBucket]


@dataclass(frozen=True)
class StatusSnapshot:
    """Everything the renderer needs. Safe to serialize to JSON for cache."""

    organization_name: str
    headline: str | None
    overall: str  # 'operational' | 'partial_outage' | 'major_outage'
    monitors: list[PublicMonitor]
    generated_at: str  # ISO timestamp

    @classmethod
    def from_json(cls, raw: str) -> "StatusSnapshot":
        data = json.loads(raw)
        return cls(
            organization_name=data["organization_name"],
            headline=data.get("headline"),
            overall=data["overall"],
            monitors=[
                PublicMonitor(
                    name=m["name"],
                    status=m["status"],
                    schedule_value=m["schedule_value"],
                    schedule_type=m["schedule_type"],
                    days=[DayBucket(**d) for d in m["days"]],
                )
                for m in data["monitors"]
            ],
            generated_at=data["generated_at"],
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


_FAILING_STATES = {"failed", "missed", "timed_out"}
_DEGRADED_STATES = {"late"}
_HEALTHY_STATES = {"healthy", "unknown"}


# Used by both the day-bucket comparator and the overall-status comparator.
# Lower index = better.
_STATE_SEVERITY = {
    "no_data": 0,
    "succeeded": 1,
    "late": 2,
    "missed": 3,
    "timed_out": 4,
    "failed": 5,
}


def _worse_state(a: str, b: str) -> str:
    return a if _STATE_SEVERITY.get(a, -1) >= _STATE_SEVERITY.get(b, -1) else b


# ── Public API ───────────────────────────────────────────────────────────────


async def load_snapshot(slug: str) -> StatusSnapshot | None:
    """Cache-aware loader. Returns ``None`` for an unknown slug.

    A ``None`` result is *also cached*, briefly, so repeated requests for
    a bogus slug do not hammer Postgres.
    """
    cache_key = _CACHE_PREFIX + slug
    if redis_client._client is not None:
        cached = await redis_client.client.get(cache_key)
        if cached:
            if cached == "__missing__":
                return None
            try:
                return StatusSnapshot.from_json(cached)
            except (ValueError, KeyError) as exc:
                log.warning("status_page_cache_parse_failed", error=str(exc))

    async with db.session() as s:
        snap = await _build_snapshot(s, slug)

    if redis_client._client is not None:
        if snap is None:
            await redis_client.client.set(cache_key, "__missing__", ex=_CACHE_TTL_SECONDS)
        else:
            await redis_client.client.set(cache_key, snap.to_json(), ex=_CACHE_TTL_SECONDS)
    return snap


async def invalidate(slug: str) -> None:
    """Drop the cache entry for one slug. Called after admin mutations."""
    if redis_client._client is None:
        return
    await redis_client.client.delete(_CACHE_PREFIX + slug)


# ── Builders ─────────────────────────────────────────────────────────────────


async def _build_snapshot(
    session: AsyncSession, slug: str
) -> StatusSnapshot | None:
    org = (
        await session.execute(
            select(Organization).where(
                Organization.status_page_slug == slug,
                Organization.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if org is None:
        return None

    monitors = (
        await session.execute(
            select(Monitor).where(
                Monitor.organization_id == org.id,
                Monitor.is_public.is_(True),
                Monitor.deleted_at.is_(None),
            )
            .order_by(Monitor.name)
        )
    ).scalars().all()

    public_monitors: list[PublicMonitor] = []
    for m in monitors:
        days = await _day_buckets(session, m.id)
        public_monitors.append(
            PublicMonitor(
                name=m.name,
                status=m.status,
                schedule_value=m.schedule_value,
                schedule_type=m.schedule_type,
                days=days,
            )
        )

    overall = _overall_status(public_monitors)

    return StatusSnapshot(
        organization_name=org.name,
        headline=org.status_page_headline or None,
        overall=overall,
        monitors=public_monitors,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


async def _day_buckets(
    session: AsyncSession, monitor_id: Any
) -> list[DayBucket]:
    """Return one bucket per day for the last ``DAY_BUCKETS`` days, oldest first.

    Buckets with no runs at all are returned as ``state='no_data'``.
    """
    today = datetime.now(timezone.utc).date()
    start_dt = datetime.combine(
        today - timedelta(days=DAY_BUCKETS - 1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )

    rows = (
        await session.execute(
            select(Run.state, Run.created_at)
            .where(
                Run.monitor_id == monitor_id,
                Run.created_at >= start_dt,
            )
        )
    ).all()

    by_day: dict[date, str] = {}
    for state, created_at in rows:
        if not isinstance(created_at, datetime):
            continue
        d = created_at.astimezone(timezone.utc).date()
        prev = by_day.get(d, "no_data")
        by_day[d] = _worse_state(prev, state or "no_data")

    buckets: list[DayBucket] = []
    for i in range(DAY_BUCKETS):
        d = today - timedelta(days=DAY_BUCKETS - 1 - i)
        buckets.append(DayBucket(date=d.isoformat(), state=by_day.get(d, "no_data")))
    return buckets


def _overall_status(monitors: list[PublicMonitor]) -> str:
    """Compute a top-line status from the per-monitor statuses.

    Rules:
    - any ``failed`` / ``missed`` / ``timed_out`` -> ``major_outage`` if
      MORE THAN HALF of monitors are unhealthy, else ``partial_outage``
    - any ``late`` -> ``partial_outage``
    - otherwise ``operational``
    """
    if not monitors:
        return "operational"

    unhealthy = sum(1 for m in monitors if m.status in _FAILING_STATES)
    degraded = sum(1 for m in monitors if m.status in _DEGRADED_STATES)

    if unhealthy:
        if unhealthy * 2 > len(monitors):
            return "major_outage"
        return "partial_outage"
    if degraded:
        return "partial_outage"
    return "operational"
