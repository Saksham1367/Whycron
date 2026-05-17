"""Monitors API tests — CRUD, tier limits, multi-tenancy isolation."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from apps.api.db import db
from apps.api.models import Monitor, Organization

VALID_CRON = "*/5 * * * *"


# ── Auth boundary ────────────────────────────────────────────────────────────


async def test_unauthenticated_monitor_request_is_401(http_client) -> None:
    response = await http_client.get("/api/v1/monitors")
    assert response.status_code == 401


# ── Create ───────────────────────────────────────────────────────────────────


async def test_create_monitor_returns_201_and_persists(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    payload = {
        "name": "Nightly Backup",
        "schedule_type": "cron",
        "schedule_value": "0 2 * * *",
        "timezone": "UTC",
        "grace_period_seconds": 120,
        "tags": ["db", "backup"],
    }
    response = await client.post("/api/v1/monitors", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Nightly Backup"
    assert data["status"] == "unknown"
    assert data["paused"] is False
    assert data["ping_token"].startswith("wcr_")
    assert data["tags"] == ["db", "backup"]

    async with db.session() as s:
        rows = (
            await s.execute(
                select(Monitor).where(
                    Monitor.organization_id == ctx["org_id"],
                    Monitor.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].ping_token == data["ping_token"]


async def test_create_monitor_rejects_invalid_cron(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/monitors",
        json={
            "name": "bad",
            "schedule_type": "cron",
            "schedule_value": "not a cron",
        },
    )
    assert response.status_code == 422


async def test_create_monitor_rejects_invalid_interval(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/monitors",
        json={
            "name": "bad",
            "schedule_type": "interval",
            "schedule_value": "abc",
        },
    )
    assert response.status_code == 422


async def test_create_monitor_402_at_free_tier_limit(
    authed_user_factory,
) -> None:
    """Free tier allows 5 monitors. The 6th must 402."""
    client, _ = await authed_user_factory()
    for i in range(5):
        r = await client.post(
            "/api/v1/monitors",
            json={
                "name": f"M{i}",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
        assert r.status_code == 201
    sixth = await client.post(
        "/api/v1/monitors",
        json={
            "name": "M6",
            "schedule_type": "cron",
            "schedule_value": VALID_CRON,
        },
    )
    assert sixth.status_code == 402
    assert "monitors" in sixth.json()["detail"].lower()


async def test_create_monitor_at_pro_tier_allows_more(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory(tier="pro")
    for i in range(6):
        r = await client.post(
            "/api/v1/monitors",
            json={
                "name": f"M{i}",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
        assert r.status_code == 201


# ── List ─────────────────────────────────────────────────────────────────────


async def test_list_returns_empty_when_no_monitors(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    response = await client.get("/api/v1/monitors")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_returns_only_my_org_monitors(
    authed_user_factory,
) -> None:
    """Multi-tenancy: org A's list must not include org B's monitors."""
    client_a, _ = await authed_user_factory()
    client_b, _ = await authed_user_factory()

    await client_a.post(
        "/api/v1/monitors",
        json={
            "name": "OrgA Monitor",
            "schedule_type": "cron",
            "schedule_value": VALID_CRON,
        },
    )
    await client_b.post(
        "/api/v1/monitors",
        json={
            "name": "OrgB Monitor",
            "schedule_type": "cron",
            "schedule_value": VALID_CRON,
        },
    )

    a_resp = await client_a.get("/api/v1/monitors")
    b_resp = await client_b.get("/api/v1/monitors")
    a_names = [m["name"] for m in a_resp.json()["items"]]
    b_names = [m["name"] for m in b_resp.json()["items"]]

    assert "OrgA Monitor" in a_names
    assert "OrgB Monitor" not in a_names
    assert "OrgB Monitor" in b_names
    assert "OrgA Monitor" not in b_names


async def test_list_supports_status_and_search_filters(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    for name in ("Alpha", "Beta", "Gamma"):
        await client.post(
            "/api/v1/monitors",
            json={
                "name": name,
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    # Force one into 'failing' to verify the status filter.
    async with db.session() as s:
        first_id = (
            await s.execute(
                select(Monitor.id).where(
                    Monitor.organization_id == ctx["org_id"],
                    Monitor.name == "Beta",
                )
            )
        ).scalar_one()
        await s.execute(
            update(Monitor).where(Monitor.id == first_id).values(status="failing")
        )
        await s.commit()

    resp = await client.get("/api/v1/monitors?status=failing")
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["name"] == "Beta"

    resp = await client.get("/api/v1/monitors?search=Alpha")
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["name"] == "Alpha"


# ── Get / Update / Delete + multi-tenancy ────────────────────────────────────


async def test_get_monitor_returns_monitor_and_recent_runs(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    created = (
        await client.post(
            "/api/v1/monitors",
            json={
                "name": "Get Test",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    ).json()
    response = await client.get(f"/api/v1/monitors/{created['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["monitor"]["name"] == "Get Test"
    assert data["recent_runs"] == []


async def test_get_monitor_404_for_other_org(authed_user_factory) -> None:
    client_a, _ = await authed_user_factory()
    client_b, _ = await authed_user_factory()
    created = (
        await client_a.post(
            "/api/v1/monitors",
            json={
                "name": "Cross-org",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    ).json()
    response = await client_b.get(f"/api/v1/monitors/{created['id']}")
    assert response.status_code == 404


async def test_update_monitor_changes_fields(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    created = (
        await client.post(
            "/api/v1/monitors",
            json={
                "name": "Original",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    ).json()
    response = await client.patch(
        f"/api/v1/monitors/{created['id']}",
        json={"name": "Renamed", "paused": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Renamed"
    assert data["paused"] is True


async def test_update_with_empty_body_is_400(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    created = (
        await client.post(
            "/api/v1/monitors",
            json={
                "name": "x",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    ).json()
    response = await client.patch(
        f"/api/v1/monitors/{created['id']}", json={}
    )
    assert response.status_code == 400


async def test_update_404_for_other_org(authed_user_factory) -> None:
    client_a, _ = await authed_user_factory()
    client_b, _ = await authed_user_factory()
    created = (
        await client_a.post(
            "/api/v1/monitors",
            json={
                "name": "Cross-org patch",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    ).json()
    response = await client_b.patch(
        f"/api/v1/monitors/{created['id']}",
        json={"name": "evil"},
    )
    assert response.status_code == 404


async def test_delete_monitor_soft_deletes(authed_user_factory) -> None:
    client, ctx = await authed_user_factory()
    created = (
        await client.post(
            "/api/v1/monitors",
            json={
                "name": "ToDelete",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    ).json()
    response = await client.delete(f"/api/v1/monitors/{created['id']}")
    assert response.status_code == 204

    # List endpoint should now hide it.
    listing = await client.get("/api/v1/monitors")
    assert listing.json()["total"] == 0

    # Row still exists with deleted_at set.
    async with db.session() as s:
        row = (
            await s.execute(
                select(Monitor).where(Monitor.id == created["id"])
            )
        ).scalar_one()
    assert row.deleted_at is not None


async def test_delete_404_for_other_org(authed_user_factory) -> None:
    client_a, _ = await authed_user_factory()
    client_b, _ = await authed_user_factory()
    created = (
        await client_a.post(
            "/api/v1/monitors",
            json={
                "name": "Theirs",
                "schedule_type": "cron",
                "schedule_value": VALID_CRON,
            },
        )
    ).json()
    response = await client_b.delete(f"/api/v1/monitors/{created['id']}")
    assert response.status_code == 404
