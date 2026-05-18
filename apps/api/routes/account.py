"""Account / organization info endpoint.

The dashboard's "settings" page reads this to show the current tier, the
feature flags, and live usage counters. Heavier endpoints (export,
deletion) live elsewhere and land in later phases.

This route also tracks terms-of-service acceptance (Phase 16). Each
``GET /api/v1/account`` response carries a ``terms`` block the dashboard
uses to decide whether to show the blocking acceptance modal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import AIExplanation, AuditLog, Monitor, Organization, User
from apps.api.routes.auth import get_current_user, require_scope
from apps.api.schemas.account import (
    AccountOut,
    TermsAcceptIn,
    TermsState,
    UsageBlock,
)
from apps.api.services.auth import AuthedUser
from apps.api.services.tier_limits import (
    ai_explanations_limit_for_tier,
    monitors_limit_for_tier,
)

router = APIRouter(prefix="/api/v1/account", tags=["account"])
log = structlog.get_logger("whycron.api.account")


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
        terms=_terms_state(user),
    )


# ── Terms-of-service acceptance ──────────────────────────────────────────────


@router.post("/accept-terms", response_model=TermsState)
async def accept_terms(
    body: TermsAcceptIn,
    request: Request,
    # NB: we use ``get_current_user`` here, not ``require_scope('admin')``,
    # so an API-key principal couldn't accept terms on a user's behalf —
    # only the human-authenticated dashboard session can.
    auth: AuthedUser = Depends(get_current_user),
) -> TermsState:
    """Record that the user explicitly accepted the published terms.

    Idempotent — re-accepting the current version is a no-op except that
    the timestamp + IP are refreshed for the audit trail.
    """
    if auth.auth_method != "jwt":
        # API-key callers can't bind a human acceptance.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Terms must be accepted from the dashboard, not via an API key.",
        )

    if body.version != settings.terms_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Terms version mismatch — please refresh the page and "
                "review the current terms before accepting."
            ),
        )

    client_ip = (request.client.host if request.client else "") or ""
    if len(client_ip) > 45:
        client_ip = client_ip[:45]

    async with db.session() as session:
        user = (
            await session.execute(select(User).where(User.id == auth.id))
        ).scalar_one()
        user.terms_version_accepted = settings.terms_version
        user.terms_accepted_at = datetime.now(timezone.utc)
        user.terms_accepted_ip = client_ip or None

        session.add(
            AuditLog(
                organization_id=auth.organization_id,
                action="terms.accepted",
                entity_type="user",
                entity_id=user.id,
                ip_address=client_ip or None,
                user_agent=(request.headers.get("user-agent", "")[:500] or None),
                diff=_terms_audit_diff(user),
            )
        )
        await session.commit()
        await session.refresh(user)

        log.info(
            "terms_accepted",
            user_id=str(user.id),
            org_id=str(auth.organization_id),
            version=user.terms_version_accepted,
        )
        return _terms_state(user)


def _terms_state(user: User) -> TermsState:
    accepted_version = user.terms_version_accepted
    return TermsState(
        current_version=settings.terms_version,
        accepted_version=accepted_version,
        accepted_at=user.terms_accepted_at,
        is_up_to_date=accepted_version == settings.terms_version,
    )


def _terms_audit_diff(user: User) -> dict[str, Any]:
    """Snapshot stored on the audit-log row so legal can reconstruct what
    the user accepted, when, and from where, without joining back to the
    live users table (which may have been mutated later)."""
    return {
        "version": user.terms_version_accepted,
        "accepted_at": (
            user.terms_accepted_at.isoformat()
            if user.terms_accepted_at
            else None
        ),
        "ip": user.terms_accepted_ip,
    }
