"""API key management + scope enforcement tests (Phase 11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from apps.api.db import db
from apps.api.models import APIKey


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _mint_key(
    client: AsyncClient, *, name: str = "ci", scopes: list[str] | None = None
) -> dict:
    payload: dict = {
        "name": name,
        "scopes": scopes if scopes is not None else ["monitors:read"],
    }
    response = await client.post("/api/v1/api-keys", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _api_key_client(plaintext: str) -> AsyncClient:
    from apps.api.main import app

    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Whycron-API-Key": plaintext},
    )


# ── Auth boundary ────────────────────────────────────────────────────────────


async def test_unauthenticated_api_keys_request_is_401(http_client) -> None:
    response = await http_client.get("/api/v1/api-keys")
    assert response.status_code == 401


async def test_garbage_api_key_is_401(http_client) -> None:
    http_client.headers["X-Whycron-API-Key"] = "wcr_live_not-a-real-key"
    response = await http_client.get("/api/v1/monitors")
    assert response.status_code == 401


async def test_wrong_prefix_api_key_is_401(http_client) -> None:
    http_client.headers["X-Whycron-API-Key"] = "pk_test_something"
    response = await http_client.get("/api/v1/monitors")
    assert response.status_code == 401


# ── Create ───────────────────────────────────────────────────────────────────


async def test_create_returns_plaintext_once_with_prefix(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/api-keys",
        json={"name": "deploy", "scopes": ["monitors:read", "runs:read"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    plaintext = body["plaintext"]
    assert plaintext.startswith("wcr_live_")
    assert len(plaintext) > 30
    assert body["key_prefix"] == plaintext[:13]
    assert set(body["scopes"]) == {"monitors:read", "runs:read"}
    assert body["revoked_at"] is None
    assert body["last_used_at"] is None
    assert "key_hash" not in body  # never expose the hash


async def test_create_rejects_unknown_scope(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/api-keys",
        json={"name": "bad", "scopes": ["monitors:nope"]},
    )
    assert response.status_code == 422


async def test_create_rejects_empty_scopes(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/api-keys", json={"name": "empty", "scopes": []}
    )
    assert response.status_code == 422


# ── List ─────────────────────────────────────────────────────────────────────


async def test_list_returns_prefix_not_plaintext(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    minted = await _mint_key(client, name="A", scopes=["monitors:read"])
    response = await client.get("/api/v1/api-keys")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["id"] == minted["id"]
    assert rows[0]["key_prefix"] == minted["key_prefix"]
    assert "plaintext" not in rows[0]
    assert "key_hash" not in rows[0]


async def test_list_is_scoped_to_caller_org(authed_user_factory) -> None:
    alice_client, _ = await authed_user_factory()
    bob_client, _ = await authed_user_factory()
    await _mint_key(alice_client, name="alice-key")
    await _mint_key(bob_client, name="bob-key-1")
    await _mint_key(bob_client, name="bob-key-2")

    alice_rows = (await alice_client.get("/api/v1/api-keys")).json()
    bob_rows = (await bob_client.get("/api/v1/api-keys")).json()
    assert {r["name"] for r in alice_rows} == {"alice-key"}
    assert {r["name"] for r in bob_rows} == {"bob-key-1", "bob-key-2"}


# ── Revoke ───────────────────────────────────────────────────────────────────


async def test_revoke_sets_revoked_at_and_invalidates_key(
    authed_user_factory,
) -> None:
    dashboard, _ = await authed_user_factory()
    minted = await _mint_key(dashboard, scopes=["monitors:read"])

    async with await _api_key_client(minted["plaintext"]) as key_client:
        ok = await key_client.get("/api/v1/monitors")
        assert ok.status_code == 200

        revoke = await dashboard.delete(f"/api/v1/api-keys/{minted['id']}")
        assert revoke.status_code == 204

        denied = await key_client.get("/api/v1/monitors")
        assert denied.status_code == 401


async def test_revoke_other_orgs_key_returns_404(authed_user_factory) -> None:
    alice, _ = await authed_user_factory()
    bob, _ = await authed_user_factory()
    minted = await _mint_key(bob)
    response = await alice.delete(f"/api/v1/api-keys/{minted['id']}")
    assert response.status_code == 404


# ── Use the key against existing routes ──────────────────────────────────────


async def test_read_scope_can_list_but_not_create_monitors(
    authed_user_factory,
) -> None:
    dashboard, _ = await authed_user_factory()
    minted = await _mint_key(dashboard, scopes=["monitors:read"])

    async with await _api_key_client(minted["plaintext"]) as key_client:
        list_resp = await key_client.get("/api/v1/monitors")
        assert list_resp.status_code == 200

        create_resp = await key_client.post(
            "/api/v1/monitors",
            json={
                "name": "from-readonly-key",
                "schedule_type": "cron",
                "schedule_value": "*/5 * * * *",
            },
        )
        assert create_resp.status_code == 403


async def test_write_scope_can_create_monitor(authed_user_factory) -> None:
    dashboard, ctx = await authed_user_factory()
    minted = await _mint_key(
        dashboard, scopes=["monitors:read", "monitors:write"]
    )

    async with await _api_key_client(minted["plaintext"]) as key_client:
        response = await key_client.post(
            "/api/v1/monitors",
            json={
                "name": "from-key",
                "schedule_type": "cron",
                "schedule_value": "*/5 * * * *",
            },
        )
        assert response.status_code == 201, response.text


async def test_admin_scope_can_list_keys(authed_user_factory) -> None:
    dashboard, _ = await authed_user_factory()
    minted = await _mint_key(dashboard, scopes=["admin"])

    async with await _api_key_client(minted["plaintext"]) as key_client:
        response = await key_client.get("/api/v1/api-keys")
        assert response.status_code == 200


async def test_non_admin_key_cannot_manage_keys(authed_user_factory) -> None:
    dashboard, _ = await authed_user_factory()
    minted = await _mint_key(dashboard, scopes=["monitors:write"])

    async with await _api_key_client(minted["plaintext"]) as key_client:
        response = await key_client.get("/api/v1/api-keys")
        assert response.status_code == 403


async def test_runs_read_scope_can_list_runs_but_not_monitors(
    authed_user_factory,
) -> None:
    dashboard, _ = await authed_user_factory()
    minted = await _mint_key(dashboard, scopes=["runs:read"])

    async with await _api_key_client(minted["plaintext"]) as key_client:
        runs = await key_client.get("/api/v1/runs")
        assert runs.status_code == 200
        monitors = await key_client.get("/api/v1/monitors")
        assert monitors.status_code == 403


# ── Expiry ───────────────────────────────────────────────────────────────────


async def test_expired_key_is_rejected(authed_user_factory) -> None:
    dashboard, _ = await authed_user_factory()
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    response = await dashboard.post(
        "/api/v1/api-keys",
        json={
            "name": "soon-expires",
            "scopes": ["monitors:read"],
            "expires_at": future.isoformat(),
        },
    )
    assert response.status_code == 201
    minted = response.json()

    # Backdate the expiry directly in the DB to simulate the key aging out.
    async with db.session() as s:
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        await s.execute(
            update(APIKey).where(APIKey.id == minted["id"]).values(expires_at=past)
        )
        await s.commit()

    async with await _api_key_client(minted["plaintext"]) as key_client:
        response = await key_client.get("/api/v1/monitors")
        assert response.status_code == 401


async def test_expires_at_in_past_is_400_on_create(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "bad",
            "scopes": ["monitors:read"],
            "expires_at": past,
        },
    )
    assert response.status_code == 422


# ── last_used_at ─────────────────────────────────────────────────────────────


async def test_successful_use_updates_last_used_at(authed_user_factory) -> None:
    dashboard, _ = await authed_user_factory()
    minted = await _mint_key(dashboard)
    assert minted["last_used_at"] is None

    async with await _api_key_client(minted["plaintext"]) as key_client:
        ok = await key_client.get("/api/v1/monitors")
        assert ok.status_code == 200

    listing = (await dashboard.get("/api/v1/api-keys")).json()
    assert listing[0]["last_used_at"] is not None
