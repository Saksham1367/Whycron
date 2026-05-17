"""Polar.sh billing integration (CONTEXT.md §7.4).

Three responsibilities:

1. **Webhook signature verification** — Polar emits webhooks signed with
   the Standard Webhooks spec: ``webhook-id``, ``webhook-timestamp``, and
   ``webhook-signature`` headers. Signing string is
   ``"{id}.{timestamp}.{body}"`` and the signature is base64-encoded
   HMAC-SHA256 with the secret as raw key bytes.

2. **Outbound Polar API calls** — create checkout sessions and customer
   portal links. ``POLAR_API_BASE`` defaults to sandbox.

3. **Event handlers** — translate Polar subscription events into Whycron
   tier transitions on the ``organizations`` table.

All Polar HTTP I/O lives in this module so the routes stay thin.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models import Organization, ProcessedPolarEvent

log = structlog.get_logger("whycron.billing")


class WebhookSignatureError(Exception):
    """Signature check failed (bad sig, stale timestamp, missing headers)."""


class PolarAPIError(RuntimeError):
    """Outbound Polar call returned a non-2xx response."""


# ── Webhook signature verification (Standard Webhooks v1) ────────────────────


_TIMESTAMP_TOLERANCE_SECONDS = 5 * 60  # CONTEXT.md §7.4


def _decode_secret(secret: str) -> bytes:
    """Polar's signing secret is base64 wrapped behind a ``whsec_`` prefix.

    The prefix is optional in some flows (legacy / older Polar projects),
    so strip if present. The raw decoded bytes are what HMAC uses as the
    key — passing the prefixed string verbatim would produce wrong sigs.
    """
    payload = secret
    for prefix in ("polar_whsec_", "whsec_"):
        if payload.startswith(prefix):
            payload = payload[len(prefix) :]
            break
    try:
        return base64.b64decode(payload)
    except Exception:  # noqa: BLE001
        # Fall back to raw bytes if the secret isn't base64. Some custom
        # setups use a plain shared-secret string.
        return secret.encode()


def verify_polar_signature(
    *, secret: str, headers: dict[str, str], body: bytes
) -> str:
    """Validate the incoming Polar webhook and return the ``webhook-id``.

    Raises :class:`WebhookSignatureError` on any failure.
    """
    if not secret:
        raise WebhookSignatureError("POLAR_WEBHOOK_SECRET is not configured")

    # Header lookup is case-insensitive in HTTP but FastAPI gives us a
    # plain dict — normalize once.
    h = {k.lower(): v for k, v in headers.items()}
    webhook_id = h.get("webhook-id")
    webhook_timestamp = h.get("webhook-timestamp")
    webhook_signature = h.get("webhook-signature")
    if not (webhook_id and webhook_timestamp and webhook_signature):
        raise WebhookSignatureError(
            "missing one of webhook-id, webhook-timestamp, webhook-signature"
        )

    try:
        ts = int(webhook_timestamp)
    except ValueError as exc:
        raise WebhookSignatureError("webhook-timestamp not an integer") from exc

    drift = abs(int(time.time()) - ts)
    if drift > _TIMESTAMP_TOLERANCE_SECONDS:
        raise WebhookSignatureError(
            f"webhook-timestamp out of tolerance ({drift}s)"
        )

    signing_string = f"{webhook_id}.{ts}.".encode() + body
    expected_digest = hmac.new(
        _decode_secret(secret), signing_string, hashlib.sha256
    ).digest()
    expected_b64 = base64.b64encode(expected_digest).decode()

    # Standard Webhooks allows multiple space-separated ``v1,<sig>`` pairs
    # so receivers can rotate keys without dropping deliveries.
    candidates = webhook_signature.split(" ")
    for candidate in candidates:
        if "," not in candidate:
            continue
        version, received = candidate.split(",", 1)
        if version != "v1":
            continue
        if hmac.compare_digest(received.strip(), expected_b64):
            return webhook_id

    raise WebhookSignatureError("no signature matched")


# ── Idempotency ──────────────────────────────────────────────────────────────


async def is_event_already_processed(
    session: AsyncSession, polar_event_id: str
) -> bool:
    existing = (
        await session.execute(
            select(ProcessedPolarEvent.polar_event_id).where(
                ProcessedPolarEvent.polar_event_id == polar_event_id
            )
        )
    ).scalar_one_or_none()
    return existing is not None


async def mark_event_processed(
    session: AsyncSession,
    *,
    polar_event_id: str,
    event_type: str,
    organization_id: uuid.UUID | None,
) -> None:
    session.add(
        ProcessedPolarEvent(
            polar_event_id=polar_event_id,
            event_type=event_type,
            organization_id=organization_id,
        )
    )


# ── Event handlers ───────────────────────────────────────────────────────────


# Polar subscription statuses we map to Whycron tier transitions. Anything
# else is logged but does not change tier.
_PAID_STATUSES = frozenset({"active", "trialing"})
_DOWNGRADE_STATUSES = frozenset({"canceled", "incomplete_expired", "unpaid"})


def _product_id_to_tier(product_id: str) -> str | None:
    """Match a Polar product ID against our env-configured tier products."""
    if product_id and product_id == settings.polar_product_pro_id:
        return "pro"
    if product_id and product_id == settings.polar_product_team_id:
        return "team"
    return None


async def handle_subscription_event(
    session: AsyncSession,
    *,
    event_type: str,
    data: dict[str, Any],
) -> uuid.UUID | None:
    """Process a ``subscription.*`` event payload. Returns the Whycron
    organization ID we touched, or ``None`` if we couldn't map it.
    """
    org_id = _resolve_org_id(data)
    if org_id is None:
        log.warning(
            "polar_event_missing_org_metadata",
            event_type=event_type,
            subscription_id=data.get("id"),
        )
        return None

    org = (
        await session.execute(
            select(Organization).where(Organization.id == org_id)
        )
    ).scalar_one_or_none()
    if org is None:
        log.warning(
            "polar_event_unknown_org",
            event_type=event_type,
            org_id=str(org_id),
        )
        return None

    polar_status = (data.get("status") or "").lower()
    product_id = data.get("product_id") or (data.get("product") or {}).get("id")
    customer_id = data.get("customer_id") or (data.get("customer") or {}).get("id")
    subscription_id = data.get("id")

    # Keep the Polar identifiers on the org row for future portal lookups.
    if customer_id:
        org.polar_customer_id = customer_id
    if subscription_id:
        org.polar_subscription_id = subscription_id

    # Decide the new tier.
    if polar_status in _PAID_STATUSES:
        tier = _product_id_to_tier(product_id) or "pro"
        org.tier = tier
        log.info(
            "polar_tier_upgraded",
            org_id=str(org_id),
            new_tier=tier,
            status=polar_status,
        )
    elif polar_status in _DOWNGRADE_STATUSES:
        org.tier = "free"
        log.info(
            "polar_tier_downgraded",
            org_id=str(org_id),
            status=polar_status,
        )
    else:
        log.info(
            "polar_event_no_tier_change",
            event_type=event_type,
            status=polar_status,
        )

    return org_id


def _resolve_org_id(data: dict[str, Any]) -> uuid.UUID | None:
    """Find a Whycron org ID inside a Polar event payload.

    We set ``metadata.whycron_org_id`` when we create the checkout, so it
    propagates onto every subscription event. Polar may also surface the
    same value on the customer if we ever attach it there.
    """
    for path in (
        ("metadata", "whycron_org_id"),
        ("customer", "metadata", "whycron_org_id"),
        ("subscription", "metadata", "whycron_org_id"),
    ):
        cursor: Any = data
        for key in path:
            if not isinstance(cursor, dict):
                cursor = None
                break
            cursor = cursor.get(key)
        if cursor:
            try:
                return uuid.UUID(str(cursor))
            except (ValueError, TypeError):
                pass
    return None


# ── Outbound Polar API ───────────────────────────────────────────────────────


def _polar_headers() -> dict[str, str]:
    if not settings.polar_api_key:
        raise PolarAPIError("POLAR_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.polar_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def create_checkout_session(
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    email: str,
    product_id: str,
    success_url: str,
) -> str:
    """Create a Polar-hosted checkout session and return its URL.

    We stamp ``whycron_org_id`` into ``metadata`` so the subsequent
    subscription webhook can route the tier flip back to the right org.
    """
    if not product_id:
        raise PolarAPIError("no product_id configured for the requested tier")

    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True
    ) as client:
        response = await client.post(
            # Trailing slash matters — Polar serves `/v1/checkouts/` and
            # 307-redirects the bare path. ``follow_redirects=True`` is a
            # safety net in case they shift the route again.
            f"{settings.polar_api_base.rstrip('/')}/v1/checkouts/",
            headers=_polar_headers(),
            json={
                "products": [product_id],
                "success_url": success_url,
                "customer_email": email,
                "metadata": {
                    "whycron_org_id": str(organization_id),
                    "whycron_user_id": str(user_id),
                },
            },
        )

    if response.status_code >= 400:
        log.warning(
            "polar_create_checkout_failed",
            status=response.status_code,
            body=response.text[:500],
        )
        raise PolarAPIError(
            f"Polar returned {response.status_code}: {response.text[:200]}"
        )

    body = response.json()
    url = body.get("url") or body.get("checkout_url")
    if not url:
        raise PolarAPIError(f"Polar response missing url field: {body!r}")
    return str(url)


async def create_customer_portal_url(*, polar_customer_id: str) -> str:
    """Mint a one-shot customer-portal link for a paying org.

    Polar's hosted portal lets users update card details, view invoices,
    and cancel without us building our own UI for those workflows.
    """
    if not polar_customer_id:
        raise PolarAPIError("organization has no polar_customer_id yet")

    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True
    ) as client:
        response = await client.post(
            # Trailing slash for the same reason as ``/v1/checkouts/``.
            f"{settings.polar_api_base.rstrip('/')}/v1/customer-sessions/",
            headers=_polar_headers(),
            json={"customer_id": polar_customer_id},
        )

    if response.status_code >= 400:
        log.warning(
            "polar_create_portal_failed",
            status=response.status_code,
            body=response.text[:500],
        )
        raise PolarAPIError(
            f"Polar returned {response.status_code}: {response.text[:200]}"
        )

    body = response.json()
    url = (
        body.get("customer_portal_url")
        or body.get("url")
        or body.get("portal_url")
    )
    if not url:
        raise PolarAPIError(f"Polar response missing portal url: {body!r}")
    return str(url)
