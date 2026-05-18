"""Authenticated admin endpoints for the status-page (Phase 14).

Lets the dashboard:
- read the current slug + headline + counts
- set / change / clear the slug
- update the headline

The actual public render lives in :mod:`apps.api.routes.status` and is
unauthenticated.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import Monitor, Organization
from apps.api.routes.auth import require_scope
from apps.api.schemas.status_page import StatusPageConfig, StatusPageUpdate
from apps.api.services import status_page
from apps.api.services.auth import AuthedUser

router = APIRouter(prefix="/api/v1/status-page", tags=["status-page"])
log = structlog.get_logger("whycron.status_page.admin")


def _public_url(slug: str | None) -> str | None:
    if not slug:
        return None
    base = (settings.app_url or "").rstrip("/")
    if not base:
        return f"/status/{slug}"
    return f"{base}/status/{slug}"


@router.get("", response_model=StatusPageConfig)
async def get_status_page(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> StatusPageConfig:
    async with db.session() as session:
        org = (
            await session.execute(
                select(Organization).where(Organization.id == auth.organization_id)
            )
        ).scalar_one()
        public_count = (
            await session.execute(
                select(func.count(Monitor.id)).where(
                    Monitor.organization_id == auth.organization_id,
                    Monitor.is_public.is_(True),
                    Monitor.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        total_count = (
            await session.execute(
                select(func.count(Monitor.id)).where(
                    Monitor.organization_id == auth.organization_id,
                    Monitor.deleted_at.is_(None),
                )
            )
        ).scalar_one()

    return StatusPageConfig(
        slug=org.status_page_slug,
        headline=org.status_page_headline,
        public_monitor_count=int(public_count or 0),
        total_monitor_count=int(total_count or 0),
        public_url=_public_url(org.status_page_slug),
    )


@router.patch("", response_model=StatusPageConfig)
async def update_status_page(
    body: StatusPageUpdate,
    auth: AuthedUser = Depends(require_scope("admin")),
) -> StatusPageConfig:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields supplied",
        )

    async with db.session() as session:
        org = (
            await session.execute(
                select(Organization).where(Organization.id == auth.organization_id)
            )
        ).scalar_one()

        old_slug = org.status_page_slug

        if "slug" in updates:
            org.status_page_slug = updates["slug"]  # may be None to clear
        if "headline" in updates:
            org.status_page_headline = updates["headline"] or None

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            # The status_page_slug column has a UNIQUE constraint. The only
            # way a commit fails is a duplicate slug claim.
            log.info(
                "status_page_slug_collision",
                org_id=str(auth.organization_id),
                attempted=updates.get("slug"),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "That status page URL is already taken. Pick another slug."
                ),
            ) from exc

        # Invalidate both the old and new cache keys so neither one serves
        # a stale snapshot after the change.
        if old_slug:
            await status_page.invalidate(old_slug)
        if org.status_page_slug:
            await status_page.invalidate(org.status_page_slug)

    # Read fresh counts via the GET handler for consistency.
    return await get_status_page(auth)  # type: ignore[arg-type]
