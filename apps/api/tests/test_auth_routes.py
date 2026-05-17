"""``/api/v1/auth/me`` integration tests + first-signin flow.

HS256 with a monkeypatched secret is used everywhere so these are fast,
deterministic, and key-free. The live RS256 Supabase round-trip lives in
``test_auth_live_supabase.py``.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import jwt as pyjwt
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from apps.api.db import db
from apps.api.models import Organization, User

TEST_SECRET = "test-secret-do-not-use-in-production-32-chars-of-padding"


def _make_token(
    secret: str = TEST_SECRET,
    *,
    sub: str | None = None,
    email: str = "newuser@authtest.example",
    full_name: str | None = "Test User",
    aud: str = "authenticated",
    extra: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": sub or str(uuid.uuid4()),
        "aud": aud,
        "iat": now,
        "exp": now + 3600,
        "email": email,
        "user_metadata": {"full_name": full_name} if full_name else {},
    }
    if extra:
        claims.update(extra)
    return pyjwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def hs256_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.api.config.settings.supabase_jwt_secret", TEST_SECRET
    )


async def _cleanup_supabase_user(supabase_user_id: str) -> None:
    async with db.session() as s:
        user = (
            await s.execute(
                select(User).where(User.supabase_user_id == supabase_user_id)
            )
        ).scalar_one_or_none()
        if user is None:
            return
        await s.execute(delete(User).where(User.id == user.id))
        await s.execute(
            delete(Organization).where(Organization.id == user.organization_id)
        )
        await s.commit()


# ── Auth boundary errors ─────────────────────────────────────────────────────


async def test_me_rejects_missing_header(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    response = await http_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


async def test_me_rejects_malformed_header(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    response = await http_client.get(
        "/api/v1/auth/me", headers={"Authorization": "NotBearer xyz"}
    )
    assert response.status_code == 401


async def test_me_rejects_empty_bearer(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    response = await http_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer "}
    )
    assert response.status_code == 401


async def test_me_rejects_forged_signature(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    token = _make_token(
        secret="totally-different-secret-with-extra-padding-bytes-here"
    )
    response = await http_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


async def test_me_rejects_expired(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    token = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
            "email": "x@y.com",
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    response = await http_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


async def test_me_rejects_service_role_token(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    """Service-role tokens (used for admin operations) must never grant
    user authentication."""
    token = _make_token(aud="service_role")
    response = await http_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


# ── First-signin happy path ──────────────────────────────────────────────────


async def test_me_creates_user_and_org_on_first_signin(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    supabase_user_id = str(uuid.uuid4())
    email = f"first-signin-{uuid.uuid4().hex[:8]}@authtest.example"
    try:
        token = _make_token(sub=supabase_user_id, email=email)
        response = await http_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["email"] == email
        assert data["supabase_user_id"] == supabase_user_id
        assert data["role"] == "owner"
        assert data["name"] == "Test User"
        assert uuid.UUID(data["user_id"])
        assert uuid.UUID(data["organization_id"])

        # Verify the rows actually landed in Postgres.
        async with db.session() as s:
            user = (
                await s.execute(
                    select(User).where(User.supabase_user_id == supabase_user_id)
                )
            ).scalar_one()
            org = (
                await s.execute(
                    select(Organization).where(
                        Organization.id == user.organization_id
                    )
                )
            ).scalar_one()
        assert user.email == email
        assert org.tier == "free"
        assert org.slug.startswith("first-signin-")
    finally:
        await _cleanup_supabase_user(supabase_user_id)


async def test_me_reuses_existing_user_on_repeat_signin(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    supabase_user_id = str(uuid.uuid4())
    email = f"repeat-{uuid.uuid4().hex[:8]}@authtest.example"
    try:
        token = _make_token(sub=supabase_user_id, email=email)
        first = await http_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        second = await http_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["user_id"] == second.json()["user_id"]
        assert first.json()["organization_id"] == second.json()["organization_id"]

        # Confirm there's only one User row for this supabase_user_id.
        async with db.session() as s:
            rows = (
                await s.execute(
                    select(User).where(
                        User.supabase_user_id == supabase_user_id
                    )
                )
            ).scalars().all()
        assert len(rows) == 1
    finally:
        await _cleanup_supabase_user(supabase_user_id)


async def test_me_falls_back_to_email_prefix_when_no_name(
    http_client: AsyncClient, hs256_secret: None
) -> None:
    """Email/password signups have no full_name in user_metadata. The
    Whycron workspace name should fall back to the email's local part."""
    supabase_user_id = str(uuid.uuid4())
    email = f"prefix-{uuid.uuid4().hex[:8]}@authtest.example"
    try:
        token = _make_token(sub=supabase_user_id, email=email, full_name=None)
        response = await http_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] is None

        async with db.session() as s:
            user = (
                await s.execute(
                    select(User).where(User.supabase_user_id == supabase_user_id)
                )
            ).scalar_one()
            org = (
                await s.execute(
                    select(Organization).where(
                        Organization.id == user.organization_id
                    )
                )
            ).scalar_one()
        assert org.name.startswith(email.split("@", 1)[0])
    finally:
        await _cleanup_supabase_user(supabase_user_id)
