"""Account / organization info endpoint.

The dashboard's "settings" page reads this to show the current tier, the
feature flags, and live usage counters. Heavier endpoints (export,
deletion) live elsewhere and land in later phases.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import AIExplanation, Monitor, Organization, User
from apps.api.routes.auth import require_scope
from apps.api.schemas.account import AccountOut, DeploymentFlags, UsageBlock
from apps.api.services.auth import AuthedUser
from apps.api.services.tier_limits import (
    ai_explanations_limit_for_tier,
    monitors_limit_for_tier,
)

router = APIRouter(prefix="/api/v1/account", tags=["account"])


@router.get("", response_model=AccountOut)
async def get_account(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> AccountOut:
    async with db.session() as session:
        org = (
            await session.execute(
                select(Organization).where(
                    Organization.id == auth.organization_id
                )
            )
        ).scalar_one_or_none()
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        user = (
            await session.execute(
                select(User).where(User.id == auth.id)
            )
        ).scalar_one()

        monitors_active = (
            await session.execute(
                select(func.count(Monitor.id)).where(
                    Monitor.organization_id == auth.organization_id,
                    Monitor.deleted_at.is_(None),
                )
            )
        ).scalar_one()

        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        explanations_this_month = (
            await session.execute(
                select(func.count(AIExplanation.id)).where(
                    AIExplanation.organization_id == auth.organization_id,
                    AIExplanation.created_at >= month_start,
                )
            )
        ).scalar_one()

    return AccountOut(
        organization_id=org.id,
        organization_name=org.name,
        organization_slug=org.slug,
        tier=org.tier,
        features=org.features or {},
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        usage=UsageBlock(
            monitors_active=int(monitors_active),
            monitors_limit=monitors_limit_for_tier(org.tier),
            ai_explanations_this_month=int(explanations_this_month),
            ai_explanations_monthly_limit=ai_explanations_limit_for_tier(org.tier),
        ),
        created_at=org.created_at,
        deployment=DeploymentFlags(
            self_host_mode=settings.self_host_mode,
            ai_enabled=settings.ai_enabled,
            slack_oauth_enabled=settings.slack_oauth_enabled,
            billing_enabled=settings.billing_enabled,
        ),
    )
