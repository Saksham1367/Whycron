"""Public status page + admin endpoints tests (Phase 14).

Covers:
- ``GET /status/{slug}`` is unauthenticated and returns HTML
- 404 for unknown slug
- private monitors never leak into the public response
- slug uniqueness across orgs
- per-monitor ``is_public`` toggle via PATCH /api/v1/monitors/{id}
- slug validation rules
- Redis cache invalidation after admin mutations
"""
from __future__ import annotations

from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from apps.api.db import db
from apps.api.models import Monitor, Organization


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _set_slug(client: AsyncClient, slug: str | None = "acme") -> dict:
    response = await client.patch(
        "/api/v1/status-page", json={"slug": slug}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_monitor(
    client: AsyncClient, name: str = "Backup", schedule: str = "*/5 * * * *"
) -> str:
    response = await client.post(
        "/api/v1/monitors",
        json={
            "name": name,
            "schedule_type": "cron",
            "schedule_value": schedule,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest_asyncio.fixture
async def unauthed_client(connected_db: None) -> AsyncClient:
    """ASGI client with no auth headers — used to hit the public route."""
    from apps.api.main import app

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Admin GET / PATCH ────────────────────────────────────────────────────────


async def test_admin_get_returns_unconfigured_by_default(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    response = await client.get("/api/v1/status-page")
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] is None
    assert body["headline"] is None
    assert body["public_url"] is None
    assert body["public_monitor_count"] == 0
    assert body["total_monitor_count"] == 0


async def test_admin_patch_sets_slug_and_headline(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    response = await client.patch(
        "/api/v1/status-page",
        json={"slug": "acme", "headline": "Acme operations status"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "acme"
    assert body["headline"] == "Acme operations status"
    assert body["public_url"].endswith("/status/acme")


async def test_admin_patch_can_clear_slug(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    await _set_slug(client, "tempslug")
    response = await client.patch("/api/v1/status-page", json={"slug": None})
    assert response.status_code == 200
    assert response.json()["slug"] is None


async def test_admin_patch_rejects_bad_slugs(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    for bad in ("a", "1abc", "ab", "ABC", "with space", "double--dash"):
        response = await client.patch(
            "/api/v1/status-page", json={"slug": bad}
        )
        assert response.status_code == 422, f"slug {bad!r} should be rejected"


async def test_slug_uniqueness_across_orgs_returns_409(
    authed_user_factory,
) -> None:
    alice, _ = await authed_user_factory()
    bob, _ = await authed_user_factory()
    await _set_slug(alice, "shared-name")
    response = await bob.patch(
        "/api/v1/status-page", json={"slug": "shared-name"}
    )
    assert response.status_code == 409


# ── Per-monitor is_public toggle ─────────────────────────────────────────────


async def test_patch_monitor_toggles_is_public(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    monitor_id = await _create_monitor(client)

    response = await client.patch(
        f"/api/v1/monitors/{monitor_id}", json={"is_public": True}
    )
    assert response.status_code == 200
    assert response.json()["is_public"] is True

    response = await client.patch(
        f"/api/v1/monitors/{monitor_id}", json={"is_public": False}
    )
    assert response.json()["is_public"] is False


# ── Public route ─────────────────────────────────────────────────────────────


async def test_public_status_404_for_unknown_slug(
    unauthed_client: AsyncClient,
) -> None:
    async with unauthed_client as c:
        response = await c.get("/status/no-such-slug-here")
    assert response.status_code == 404


async def test_public_status_serves_html_without_auth(
    authed_user_factory, unauthed_client: AsyncClient
) -> None:
    admin, _ = await authed_user_factory()
    await _set_slug(admin, "publictest")
    monitor_id = await _create_monitor(admin, name="Nightly Backup")
    await admin.patch(
        f"/api/v1/monitors/{monitor_id}", json={"is_public": True}
    )

    async with unauthed_client as c:
        response = await c.get("/status/publictest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "Nightly Backup" in body
    assert "System status" in body
    # Sanity: no auth-protected words leak (e.g. ``api_key``, ``user_id``,
    # ``supabase_user_id``).
    assert "supabase_user_id" not in body
    assert "api_key" not in body


async def test_public_status_hides_private_monitors(
    authed_user_factory, unauthed_client: AsyncClient
) -> None:
    admin, _ = await authed_user_factory()
    await _set_slug(admin, "privatetest")
    public_id = await _create_monitor(admin, name="Visible Public")
    private_id = await _create_monitor(admin, name="Hidden Private")
    await admin.patch(
        f"/api/v1/monitors/{public_id}", json={"is_public": True}
    )
    # private_id stays is_public=False by default

    async with unauthed_client as c:
        response = await c.get("/status/privatetest")
    assert response.status_code == 200
    body = response.text
    assert "Visible Public" in body
    assert "Hidden Private" not in body

    # JSON variant should also exclude it.
    async with unauthed_client as c2:
        json_response = await c2.get("/status/privatetest.json")
    data = json_response.json()
    names = [m["name"] for m in data["monitors"]]
    assert names == ["Visible Public"]


async def test_public_status_after_unflagging_no_longer_lists_monitor(
    authed_user_factory, unauthed_client: AsyncClient
) -> None:
    admin, _ = await authed_user_factory()
    await _set_slug(admin, "togglepage")
    monitor_id = await _create_monitor(admin, name="Toggle Job")
    await admin.patch(
        f"/api/v1/monitors/{monitor_id}", json={"is_public": True}
    )

    async with unauthed_client as c:
        first = await c.get("/status/togglepage.json")
    assert "Toggle Job" in [m["name"] for m in first.json()["monitors"]]

    await admin.patch(
        f"/api/v1/monitors/{monitor_id}", json={"is_public": False}
    )
    async with unauthed_client as c:
        second = await c.get("/status/togglepage.json")
    assert second.json()["monitors"] == []


async def test_overall_status_reflects_underlying_states(
    authed_user_factory, unauthed_client: AsyncClient
) -> None:
    admin, ctx = await authed_user_factory()
    await _set_slug(admin, "overallcheck")
    m_good = await _create_monitor(admin, name="Good")
    m_bad = await _create_monitor(admin, name="Bad")
    await admin.patch(f"/api/v1/monitors/{m_good}", json={"is_public": True})
    await admin.patch(f"/api/v1/monitors/{m_bad}", json={"is_public": True})

    async with db.session() as s:
        await s.execute(
            update(Monitor).where(Monitor.id == m_bad).values(status="failing")
        )
        await s.commit()

    async with unauthed_client as c:
        response = await c.get("/status/overallcheck.json")
    body = response.json()
    # One of two monitors failing → "partial_outage". Two of two would be major.
    assert body["overall"] == "partial_outage"


async def test_public_status_uses_cache_on_repeat_request(
    authed_user_factory, unauthed_client: AsyncClient
) -> None:
    """Mutating the org after the snapshot is cached must not be visible
    until the cache is invalidated (proves caching is engaged)."""
    admin, _ = await authed_user_factory()
    await _set_slug(admin, "cachecheck")
    monitor_id = await _create_monitor(admin, name="Cache Probe")
    await admin.patch(
        f"/api/v1/monitors/{monitor_id}", json={"is_public": True}
    )

    async with unauthed_client as c:
        first = await c.get("/status/cachecheck.json")
    assert "Cache Probe" in [m["name"] for m in first.json()["monitors"]]

    # Sneak a name change directly via SQL — bypassing the route so the
    # admin-side cache invalidation is NOT triggered. The public hit
    # should still return the OLD name from cache.
    async with db.session() as s:
        await s.execute(
            update(Monitor).where(Monitor.id == monitor_id).values(name="Renamed Probe")
        )
        await s.commit()

    async with unauthed_client as c:
        second = await c.get("/status/cachecheck.json")
    names = [m["name"] for m in second.json()["monitors"]]
    assert "Cache Probe" in names
    assert "Renamed Probe" not in names
