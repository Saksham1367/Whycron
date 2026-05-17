"""Checkout + customer portal endpoint tests with mocked Polar HTTP."""
from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import select

from apps.api.db import db
from apps.api.models import Organization

PRO_PRODUCT_ID = "prod_pro_test_xyz"


class _FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient used by the billing service."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._responses.pop(0)


@pytest.fixture
def polar_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.api.config.settings.polar_api_key", "polar_at_fake_key"
    )
    monkeypatch.setattr(
        "apps.api.config.settings.polar_product_pro_id", PRO_PRODUCT_ID
    )
    monkeypatch.setattr(
        "apps.api.config.settings.polar_api_base",
        "https://sandbox-api.polar.sh",
    )


# ── /checkout ────────────────────────────────────────────────────────────────


async def test_checkout_returns_polar_url(
    polar_config: None, monkeypatch: pytest.MonkeyPatch, authed_user_factory
) -> None:
    fake = _FakeAsyncClient(
        [_FakeResponse(200, {"id": "co_001", "url": "https://polar/checkout/co_001"})]
    )
    monkeypatch.setattr(
        "apps.api.services.billing.httpx.AsyncClient",
        lambda **kwargs: fake,
    )

    client, ctx = await authed_user_factory(tier="free")
    response = await client.post("/api/v1/billing/checkout", json={"tier": "pro"})
    assert response.status_code == 200
    body = response.json()
    assert body["checkout_url"] == "https://polar/checkout/co_001"

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"].endswith("/v1/checkouts/")
    assert call["json"]["products"] == [PRO_PRODUCT_ID]
    assert call["json"]["customer_email"] == ctx["email"]
    assert call["json"]["metadata"]["whycron_org_id"] == str(ctx["org_id"])
    assert call["json"]["metadata"]["whycron_user_id"] == str(ctx["user_id"])
    assert "Bearer polar_at_fake_key" in call["headers"]["Authorization"]


async def test_checkout_503_when_product_not_configured(
    monkeypatch: pytest.MonkeyPatch, authed_user_factory
) -> None:
    monkeypatch.setattr(
        "apps.api.config.settings.polar_product_pro_id", ""
    )
    client, _ = await authed_user_factory(tier="free")
    response = await client.post("/api/v1/billing/checkout", json={"tier": "pro"})
    assert response.status_code == 503


async def test_checkout_502_when_polar_errors(
    polar_config: None, monkeypatch: pytest.MonkeyPatch, authed_user_factory
) -> None:
    fake = _FakeAsyncClient(
        [_FakeResponse(400, {"detail": "bad product_id"})]
    )
    monkeypatch.setattr(
        "apps.api.services.billing.httpx.AsyncClient",
        lambda **kwargs: fake,
    )
    client, _ = await authed_user_factory(tier="free")
    response = await client.post("/api/v1/billing/checkout", json={"tier": "pro"})
    assert response.status_code == 502


async def test_checkout_requires_auth(http_client) -> None:
    response = await http_client.post(
        "/api/v1/billing/checkout", json={"tier": "pro"}
    )
    assert response.status_code == 401


# ── /portal ──────────────────────────────────────────────────────────────────


async def test_portal_404_when_no_polar_customer_yet(
    polar_config: None, authed_user_factory
) -> None:
    """Free-tier user who never paid has no polar_customer_id."""
    client, _ = await authed_user_factory(tier="free")
    response = await client.get("/api/v1/billing/portal")
    assert response.status_code == 404


async def test_portal_returns_url_for_paying_org(
    polar_config: None, monkeypatch: pytest.MonkeyPatch, authed_user_factory
) -> None:
    fake = _FakeAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "id": "cs_001",
                    "customer_portal_url": "https://polar/portal/abc",
                },
            )
        ]
    )
    monkeypatch.setattr(
        "apps.api.services.billing.httpx.AsyncClient",
        lambda **kwargs: fake,
    )

    client, ctx = await authed_user_factory(tier="pro")
    # Stamp the org with a Polar customer ID like a real subscription would.
    async with db.session() as s:
        org = (
            await s.execute(
                select(Organization).where(Organization.id == ctx["org_id"])
            )
        ).scalar_one()
        org.polar_customer_id = "cus_real_001"
        await s.commit()

    response = await client.get("/api/v1/billing/portal")
    assert response.status_code == 200
    assert response.json()["portal_url"] == "https://polar/portal/abc"

    assert len(fake.calls) == 1
    assert fake.calls[0]["json"]["customer_id"] == "cus_real_001"


# ── /tiers ───────────────────────────────────────────────────────────────────


async def test_tiers_returns_three_options(
    polar_config: None, authed_user_factory
) -> None:
    client, _ = await authed_user_factory()
    response = await client.get("/api/v1/billing/tiers")
    assert response.status_code == 200
    tiers = response.json()["tiers"]
    assert {t["id"] for t in tiers} == {"free", "pro", "team"}
    pro = next(t for t in tiers if t["id"] == "pro")
    assert pro["price_usd_monthly"] == 9
    assert pro["available"] is True  # because polar_config set the product id
