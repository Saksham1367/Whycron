"""Monitors CRUD endpoints.

Every query filters by ``auth.organization_id`` (CLAUDE.md rule 3 — the
multi-tenancy boundary). Create enforces the per-tier monitor cap. Update
+ delete soft-update and audit-log the change. Reads paginate with a
sensible default and bounded max.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import db
from apps.api.models import AuditLog, Monitor, Run
from apps.api.routes.auth import get_current_user
from apps.api.schemas.monitor import (
    MonitorCreate,
    MonitorOut,
    MonitorUpdate,
)
from apps.api.services import analytics
from apps.api.services.auth import AuthedUser
from apps.api.services.tier_limits import (
    generate_ping_token,
    is_unlimited,
    monitors_limit_for_tier,
)

router = APIRouter(prefix="/api/v1/monitors", tags=["monitors"])
log = structlog.get_logger("whycron.api.monitors")


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _load_monitor_or_404(
    session: AsyncSession, monitor_id: uuid.UUID, org_id: uuid.UUID
) -> Monitor:
    monitor = (
        await session.execute(
            select(Monitor).where(
                Monitor.id == monitor_id,
                Monitor.organization_id == org_id,
                Monitor.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found",
        )
    return monitor


async def _load_org_tier(session: AsyncSession, org_id: uuid.UUID) -> str:
    from apps.api.models import Organization

    tier = (
        await session.execute(
            select(Organization.tier).where(Organization.id == org_id)
        )
    ).scalar_one_or_none()
    return tier or "free"


def _audit(
    *,
    auth: AuthedUser,
    request: Request,
    action: str,
    entity_id: uuid.UUID,
    diff: dict[str, Any] | None = None,
) -> AuditLog:
    return AuditLog(
        organization_id=auth.organization_id,
        user_id=auth.id,
        action=action,
        entity_type="monitor",
        entity_id=entity_id,
        diff=diff,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent", "") or None)[:500]
        if request.headers.get("user-agent")
        else None,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=dict[str, Any])
async def list_monitors(
    auth: AuthedUser = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    async with db.session() as session:
        base = select(Monitor).where(
            Monitor.organization_id == auth.organization_id,
            Monitor.deleted_at.is_(None),
        )
        if status_filter:
            base = base.where(Monitor.status == status_filter)
        if tag:
            base = base.where(Monitor.tags.any(tag))
        if search:
            base = base.where(Monitor.name.ilike(f"%{search}%"))

        total = (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        items = (
            await session.execute(
                base.order_by(Monitor.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
    return {
        "items": [MonitorOut.model_validate(m).model_dump(mode="json") for m in items],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "",
    response_model=MonitorOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitor(
    body: MonitorCreate,
    request: Request,
    auth: AuthedUser = Depends(get_current_user),
) -> MonitorOut:
    async with db.session() as session:
        # Tier-limit enforcement.
        tier = await _load_org_tier(session, auth.organization_id)
        limit = monitors_limit_for_tier(tier)
        if not is_unlimited(limit):
            existing = (
                await session.execute(
                    select(func.count(Monitor.id)).where(
                        Monitor.organization_id == auth.organization_id,
                        Monitor.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
            if existing >= limit:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=(
                        f"Tier '{tier}' allows up to {limit} monitors. "
                        "Upgrade to add more."
                    ),
                )

        monitor = Monitor(
            organization_id=auth.organization_id,
            name=body.name,
            ping_token=generate_ping_token(),
            schedule_type=body.schedule_type,
            schedule_value=body.schedule_value,
            timezone=body.timezone,
            grace_period_seconds=body.grace_period_seconds,
            expected_runtime_seconds=body.expected_runtime_seconds,
            tags=body.tags,
            notification_settings=body.notification_settings,
        )
        session.add(monitor)
        await session.flush()
        session.add(
            _audit(
                auth=auth,
                request=request,
                action="monitor.create",
                entity_id=monitor.id,
                diff={"after": {"name": body.name}},
            )
        )
        await session.commit()

        # Conversion-funnel signal: how many users get past their first
        # monitor? Property values are stable identifiers + counts only —
        # nothing user-typed (name, logs) flows to PostHog.
        analytics.capture(
            distinct_id=auth.id,
            event="monitor_created",
            properties={
                "organization_id": str(auth.organization_id),
                "tier": tier,
                "schedule_type": body.schedule_type,
            },
        )

        return MonitorOut.model_validate(monitor)


@router.get("/{monitor_id}", response_model=dict[str, Any])
async def get_monitor(
    monitor_id: uuid.UUID,
    auth: AuthedUser = Depends(get_current_user),
    runs_limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    async with db.session() as session:
        monitor = await _load_monitor_or_404(
            session, monitor_id, auth.organization_id
        )
        recent_runs = (
            await session.execute(
                select(Run)
                .where(Run.monitor_id == monitor.id)
                .order_by(Run.created_at.desc())
                .limit(runs_limit)
            )
        ).scalars().all()
    return {
        "monitor": MonitorOut.model_validate(monitor).model_dump(mode="json"),
        "recent_runs": [
            {
                "id": str(r.id),
                "state": r.state,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "duration_ms": r.duration_ms,
                "exit_code": r.exit_code,
                "created_at": r.created_at.isoformat(),
            }
            for r in recent_runs
        ],
    }


@router.patch("/{monitor_id}", response_model=MonitorOut)
async def update_monitor(
    monitor_id: uuid.UUID,
    body: MonitorUpdate,
    request: Request,
    auth: AuthedUser = Depends(get_current_user),
) -> MonitorOut:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields supplied",
        )

    async with db.session() as session:
        monitor = await _load_monitor_or_404(
            session, monitor_id, auth.organization_id
        )

        before: dict[str, Any] = {
            "name": monitor.name,
            "schedule_value": monitor.schedule_value,
            "paused": monitor.paused,
        }
        for field, value in updates.items():
            setattr(monitor, field, value)
        await session.flush()

        session.add(
            _audit(
                auth=auth,
                request=request,
                action="monitor.update",
                entity_id=monitor.id,
                diff={"before": before, "after": updates},
            )
        )
        await session.commit()
        # ``onupdate=func.now()`` on the timestamp mixin means SQLAlchemy
        # treats ``updated_at`` as server-computed after an UPDATE. Refresh
        # so the response carries the fresh value instead of trying to
        # lazy-load it during model serialization.
        await session.refresh(monitor)
        return MonitorOut.model_validate(monitor)


@router.delete(
    "/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_monitor(
    monitor_id: uuid.UUID,
    request: Request,
    auth: AuthedUser = Depends(get_current_user),
) -> None:
    async with db.session() as session:
        monitor = await _load_monitor_or_404(
            session, monitor_id, auth.organization_id
        )
        monitor.deleted_at = datetime.now(timezone.utc)
        session.add(
            _audit(
                auth=auth,
                request=request,
                action="monitor.delete",
                entity_id=monitor.id,
            )
        )
        await session.commit()
