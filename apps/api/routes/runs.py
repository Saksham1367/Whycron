"""Runs read endpoints + AI-explanation feedback.

Runs are append-only event records (CONTEXT.md §4.2.3) so there is no
write API for them — the ping endpoint creates them. The only mutation
this router exposes is recording user thumbs-up/down on an AI explanation.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import db
from apps.api.models import AIExplanation, Run
from apps.api.routes.auth import require_scope
from apps.api.schemas.run import (
    AIExplanationOut,
    FeedbackBody,
    RunDetail,
    RunOut,
)
from apps.api.services.auth import AuthedUser

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])
log = structlog.get_logger("whycron.api.runs")


async def _load_run_or_404(
    session: AsyncSession, run_id: uuid.UUID, org_id: uuid.UUID
) -> Run:
    run = (
        await session.execute(
            select(Run).where(
                Run.id == run_id,
                Run.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    return run


@router.get("", response_model=dict[str, Any])
async def list_runs(
    auth: AuthedUser = Depends(require_scope("runs:read")),
    monitor_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    async with db.session() as session:
        base = select(Run).where(Run.organization_id == auth.organization_id)
        if monitor_id is not None:
            base = base.where(Run.monitor_id == monitor_id)
        if state is not None:
            base = base.where(Run.state == state)
        if since is not None:
            base = base.where(Run.created_at >= since)
        if until is not None:
            base = base.where(Run.created_at <= until)

        total = (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        items = (
            await session.execute(
                base.order_by(Run.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
    return {
        "items": [RunOut.model_validate(r).model_dump(mode="json") for r in items],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: uuid.UUID,
    auth: AuthedUser = Depends(require_scope("runs:read")),
) -> RunDetail:
    async with db.session() as session:
        run = await _load_run_or_404(session, run_id, auth.organization_id)
        explanation = (
            await session.execute(
                select(AIExplanation)
                .where(AIExplanation.run_id == run.id)
                .order_by(AIExplanation.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    out = RunDetail.model_validate(run)
    if explanation is not None:
        out = out.model_copy(
            update={"explanation": AIExplanationOut.model_validate(explanation)}
        )
    return out


@router.post(
    "/{run_id}/feedback", status_code=status.HTTP_204_NO_CONTENT
)
async def record_feedback(
    run_id: uuid.UUID,
    body: FeedbackBody,
    auth: AuthedUser = Depends(require_scope("runs:read")),
) -> None:
    async with db.session() as session:
        # 404 if the run isn't ours.
        await _load_run_or_404(session, run_id, auth.organization_id)
        explanation = (
            await session.execute(
                select(AIExplanation)
                .where(AIExplanation.run_id == run_id)
                .order_by(AIExplanation.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if explanation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No AI explanation exists for this run yet",
            )
        explanation.user_feedback = body.feedback
        await session.commit()
