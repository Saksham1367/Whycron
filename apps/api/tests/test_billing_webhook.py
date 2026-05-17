"""Webhook handler integration tests — idempotency + tier transitions.

These send synthetic Polar payloads through the real handler (no network).
Signatures are computed with the same helper the tests in
``test_billing_signature.py`` use, against a monkeypatched secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from sqlalchemy import select

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import Organization, ProcessedPolarEvent

TEST_SECRET_RAW = b"polar-webhook-test-secret-bytes-32-chars+"
TEST_SECRET = base64.b64encode(TEST_SECRET_RAW).decode()

PRO_PRODUCT_ID = "prod_pro_test_xyz"


@pytest.fixture
def polar_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.api.config.settings.polar_webhook_secret", TEST_SECRET
    )
    monkeypatch.setattr(
        "apps.api.config.settings.polar_product_pro_id", PRO_PRODUCT_ID
    )


def _sign_and_post_args(
    body_obj: dict[str, Any],
    *,
    webhook_id: str = "evt_test_001",
    timestamp: int | None = None,
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(body_obj, separators=(",", ":"), sort_keys=True).encode()
    ts = timestamp if timestamp is not None else int(time.time())
    signing_string = f"{webhook_id}.{ts}.".encode() + body
    digest = hmac.new(TEST_SECRET_RAW, signing_string, hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode()
    headers = {
        "webhook-id": webhook_id,
        "webhook-timestamp": str(ts),
        "webhook-signature": f"v1,{sig}",
        "content-type": "application/json",
    }
    return body, headers


def _subscription_event(
    *,
    org_id: str,
    status: str,
    customer_id: str = "cus_test_001",
    subscription_id: str = "sub_test_001",
    event_type: str = "subscription.created",
) -> dict[str, Any]:
    return {
        "type": event_type,
        "data": {
            "id": subscription_id,
            "status": status,
            "customer_id": customer_id,
            "product_id": PRO_PRODUCT_ID,
            "metadata": {"whycron_org_id": org_id},
        },
    }


# ── Signature path ───────────────────────────────────────────────────────────


async def test_webhook_rejects_unsigned(
    http_client, polar_secret_env: None
) -> None:
    response = await http_client.post(
        "/api/v1/billing/webhook",
        content=b'{"hello":"world"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401


async def test_webhook_rejects_bad_signature(
    http_client, polar_secret_env: None
) -> None:
    body, headers = _sign_and_post_args({"type": "x", "data": {}})
    headers["webhook-signature"] = "v1,definitely-wrong-base64"
    response = await http_client.post(
        "/api/v1/billing/webhook", content=body, headers=headers
    )
    assert response.status_code == 401


# ── Tier transitions ─────────────────────────────────────────────────────────


async def test_subscription_active_upgrades_org_to_pro(
    http_client, polar_secret_env: None, authed_user_factory
) -> None:
    _, ctx = await authed_user_factory(tier="free")
    body, headers = _sign_and_post_args(
        _subscription_event(
            org_id=str(ctx["org_id"]), status="active",
            event_type="subscription.active",
        )
    )
    response = await http_client.post(
        "/api/v1/billing/webhook", content=body, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    async with db.session() as s:
        org = (
            await s.execute(
                select(Organization).where(Organization.id == ctx["org_id"])
            )
        ).scalar_one()
    assert org.tier == "pro"
    assert org.polar_customer_id == "cus_test_001"
    assert org.polar_subscription_id == "sub_test_001"


async def test_subscription_canceled_downgrades_to_free(
    http_client, polar_secret_env: None, authed_user_factory
) -> None:
    _, ctx = await authed_user_factory(tier="pro")
    # First, set polar IDs so this looks like a real paid org.
    async with db.session() as s:
        org = (
            await s.execute(
                select(Organization).where(Organization.id == ctx["org_id"])
            )
        ).scalar_one()
        org.polar_customer_id = "cus_test_002"
        org.polar_subscription_id = "sub_test_002"
        await s.commit()

    body, headers = _sign_and_post_args(
        _subscription_event(
            org_id=str(ctx["org_id"]),
            status="canceled",
            customer_id="cus_test_002",
            subscription_id="sub_test_002",
            event_type="subscription.canceled",
        ),
        webhook_id="evt_test_002",
    )
    response = await http_client.post(
        "/api/v1/billing/webhook", content=body, headers=headers
    )
    assert response.status_code == 200

    async with db.session() as s:
        org = (
            await s.execute(
                select(Organization).where(Organization.id == ctx["org_id"])
            )
        ).scalar_one()
    assert org.tier == "free"


# ── Idempotency ──────────────────────────────────────────────────────────────


async def test_duplicate_event_is_skipped(
    http_client, polar_secret_env: None, authed_user_factory
) -> None:
    _, ctx = await authed_user_factory(tier="free")
    payload = _subscription_event(
        org_id=str(ctx["org_id"]),
        status="active",
        event_type="subscription.active",
    )
    body, headers = _sign_and_post_args(
        payload, webhook_id="evt_dup_001"
    )

    first = await http_client.post(
        "/api/v1/billing/webhook", content=body, headers=headers
    )
    assert first.status_code == 200
    assert first.json()["status"] == "ok"

    # Same event-id arrives again; we must NOT re-apply the tier flip.
    # To prove the no-op we first revert the tier server-side and then
    # re-deliver: the second delivery should leave the org as 'free'.
    async with db.session() as s:
        org = (
            await s.execute(
                select(Organization).where(Organization.id == ctx["org_id"])
            )
        ).scalar_one()
        org.tier = "free"
        await s.commit()

    # Same id, must re-sign (timestamp regen would be a different id).
    body2, headers2 = _sign_and_post_args(
        payload, webhook_id="evt_dup_001"
    )
    second = await http_client.post(
        "/api/v1/billing/webhook", content=body2, headers=headers2
    )
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    async with db.session() as s:
        org = (
            await s.execute(
                select(Organization).where(Organization.id == ctx["org_id"])
            )
        ).scalar_one()
    assert org.tier == "free"  # the duplicate did NOT re-upgrade

    # Confirm the processed_polar_events row exists.
    async with db.session() as s:
        rec = (
            await s.execute(
                select(ProcessedPolarEvent).where(
                    ProcessedPolarEvent.polar_event_id == "evt_dup_001"
                )
            )
        ).scalar_one()
    assert rec.event_type == "subscription.active"


# ── Missing metadata / unknown org ───────────────────────────────────────────


async def test_event_missing_org_metadata_is_recorded_but_noop(
    http_client, polar_secret_env: None
) -> None:
    """Polar event with no whycron_org_id should not crash. We record the
    event so duplicates are de-duped and respond 200."""
    payload = {
        "type": "subscription.active",
        "data": {
            "id": "sub_unmapped",
            "status": "active",
            "customer_id": "cus_unmapped",
            "product_id": PRO_PRODUCT_ID,
            "metadata": {},
        },
    }
    body, headers = _sign_and_post_args(payload, webhook_id="evt_unmapped")
    response = await http_client.post(
        "/api/v1/billing/webhook", content=body, headers=headers
    )
    assert response.status_code == 200

    async with db.session() as s:
        rec = (
            await s.execute(
                select(ProcessedPolarEvent).where(
                    ProcessedPolarEvent.polar_event_id == "evt_unmapped"
                )
            )
        ).scalar_one()
    assert rec.organization_id is None


# ── Unknown event types ──────────────────────────────────────────────────────


async def test_unmapped_event_type_is_ignored_but_recorded(
    http_client, polar_secret_env: None
) -> None:
    payload = {"type": "checkout.created", "data": {"id": "co_x"}}
    body, headers = _sign_and_post_args(payload, webhook_id="evt_other")
    response = await http_client.post(
        "/api/v1/billing/webhook", content=body, headers=headers
    )
    assert response.status_code == 200

    async with db.session() as s:
        rec = (
            await s.execute(
                select(ProcessedPolarEvent).where(
                    ProcessedPolarEvent.polar_event_id == "evt_other"
                )
            )
        ).scalar_one()
    assert rec.event_type == "checkout.created"


@pytest.fixture(autouse=True)
async def _wipe_processed_polar_events(connected_db: None):
    """Each test starts with a clean processed_polar_events table so
    re-runs don't see leftover IDs from previous tests."""
    from sqlalchemy import delete

    yield
    async with db.session() as s:
        await s.execute(delete(ProcessedPolarEvent))
        await s.commit()
