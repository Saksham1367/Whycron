"""Billing routes — checkout, customer portal, and the Polar webhook.

The webhook endpoint is *unauthenticated* (Polar can't carry a Whycron
JWT) but every other route requires the dashboard JWT and operates on the
authenticated user's org.
"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import Organization
from apps.api.routes.auth import require_scope
from apps.api.schemas.billing import CheckoutCreate, CheckoutOut, PortalOut
from apps.api.services.auth import AuthedUser
from apps.api.services.billing import (
    PolarAPIError,
    WebhookSignatureError,
    create_checkout_session,
    create_customer_portal_url,
    handle_subscription_event,
    is_event_already_processed,
    mark_event_processed,
    verify_polar_signature,
)
from apps.api.services.tier_limits import is_unlimited, monitors_limit_for_tier

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
log = structlog.get_logger("whycron.api.billing")


# ── Webhook (no auth) ────────────────────────────────────────────────────────


@router.post("/webhook", include_in_schema=False)
async def polar_webhook(request: Request) -> dict[str, str]:
    """Receive subscription events from Polar.

    Verifies signature + timestamp tolerance, checks idempotency, dispatches
    on event ``type``, and finally records the event so duplicates are
    no-ops. Always responds 200 once we've decided to process a delivery —
    Polar treats anything non-2xx as a retry signal.
    """
    body = await request.body()
    headers = dict(request.headers)

    try:
        event_id = verify_polar_signature(
            secret=settings.polar_webhook_secret,
            headers=headers,
            body=body,
        )
    except WebhookSignatureError as exc:
        log.warning("polar_webhook_signature_rejected", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Signature check failed: {exc}",
        ) from exc

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        ) from exc

    event_type = str(payload.get("type") or "")
    data: dict[str, Any] = payload.get("data") or {}

    async with db.session() as session:
        if await is_event_already_processed(session, event_id):
            log.info("polar_webhook_duplicate_skipped", event_id=event_id)
            return {"status": "duplicate"}

        touched_org: Any = None
        if event_type.startswith("subscription."):
            touched_org = await handle_subscription_event(
                session, event_type=event_type, data=data
            )
        else:
            # Unknown / unmapped event types are recorded for idempotency
            # but produce no state change.
            log.info("polar_webhook_event_ignored", event_type=event_type)

        await mark_event_processed(
            session,
            polar_event_id=event_id,
            event_type=event_type,
            organization_id=touched_org,
        )
        await session.commit()

    return {"status": "ok"}


# ── Authenticated routes ─────────────────────────────────────────────────────


@router.post("/checkout", response_model=CheckoutOut)
async def start_checkout(
    body: CheckoutCreate,
    auth: AuthedUser = Depends(require_scope("admin")),
) -> CheckoutOut:
    if not settings.billing_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Billing is not available on this Whycron instance. "
                "Self-host deployments have all features unlocked but "
                "without paid-tier upgrades. Hosted plans live at "
                "whycron.com."
                if settings.self_host_mode
                else "Billing is not configured on this Whycron instance."
            ),
        )

    product_id = (
        settings.polar_product_pro_id
        if body.tier == "pro"
        else settings.polar_product_team_id
    )
    if not product_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Billing for the '{body.tier}' tier is not configured yet. "
                "Set the corresponding POLAR_PRODUCT_*_ID in .env."
            ),
        )

    # Send the user back to the SPA, not the API. ``frontend_url`` is a
    # separate setting because the dashboard and the backend run on
    # different ports / hostnames.
    success_url = f"{settings.frontend_url.rstrip('/')}/account?upgraded=true"

    try:
        url = await create_checkout_session(
            organization_id=auth.organization_id,
            user_id=auth.id,
            email=auth.email,
            product_id=product_id,
            success_url=success_url,
        )
    except PolarAPIError as exc:
        log.warning(
            "checkout_creation_failed",
            org_id=str(auth.organization_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return CheckoutOut(checkout_url=url)


@router.get("/portal", response_model=PortalOut)
async def open_portal(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> PortalOut:
    async with db.session() as session:
        org = (
            await session.execute(
                select(Organization).where(Organization.id == auth.organization_id)
            )
        ).scalar_one()
        polar_customer_id = org.polar_customer_id

    if not polar_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This organization has no Polar customer yet. Subscribe to a "
                "paid tier first; the portal becomes available afterwards."
            ),
        )

    try:
        url = await create_customer_portal_url(
            polar_customer_id=polar_customer_id
        )
    except PolarAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return PortalOut(portal_url=url)


# Tiny convenience: surface the tier-config snapshot so the dashboard can
# render upgrade copy without re-deriving the prices client-side.
@router.get("/tiers", response_model=dict[str, Any])
async def tier_info(
    _auth: AuthedUser = Depends(require_scope("admin")),
) -> dict[str, Any]:
    return {
        "tiers": [
            {
                "id": "free",
                "name": "Free",
                "monitors_limit": monitors_limit_for_tier("free"),
                "price_usd_monthly": 0,
                "available": True,
            },
            {
                "id": "pro",
                "name": "Pro",
                "monitors_limit": monitors_limit_for_tier("pro"),
                "price_usd_monthly": 9,
                "available": bool(settings.polar_product_pro_id),
            },
            {
                "id": "team",
                "name": "Team",
                "monitors_limit": monitors_limit_for_tier("team"),
                "price_usd_monthly": 29,
                "available": bool(settings.polar_product_team_id),
            },
        ],
        "unlimited_sentinel": -1,
        "_unlimited_helper": "monitors_limit == -1 means no cap on that tier",
        "_is_unlimited_pro": is_unlimited(monitors_limit_for_tier("pro")),
    }
