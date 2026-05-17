"""Live Supabase auth round-trip — gated on a real project being configured.

This test exercises the full path: it creates a temporary user via the
Supabase admin API, signs in to receive a real JWT, calls our
``/api/v1/auth/me`` with that JWT, and then deletes the temporary user.

Skipped automatically when Supabase env vars are not present.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import Organization, User
from apps.api.services.auth import _reset_jwks_client

_SUPABASE_CONFIGURED = bool(
    settings.supabase_url
    and settings.supabase_anon_key
    and settings.supabase_service_role_key
)


@pytest.mark.skipif(
    not _SUPABASE_CONFIGURED,
    reason="Supabase env vars not configured — skipping live auth round-trip",
)
async def test_live_supabase_jwt_round_trip(http_client) -> None:
    # Make sure the JWKS client isn't carrying state from a different test
    # process. Cheap reset; no-op on HS256 projects.
    _reset_jwks_client()

    base_url = settings.supabase_url.rstrip("/")
    admin_headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    email = f"whycron-live-{uuid.uuid4().hex[:10]}@authtest.example"
    password = "TestPass!" + uuid.uuid4().hex[:16]
    supabase_user_id: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as supa:
        try:
            # 1. Create a temporary user via the admin API.
            create_resp = await supa.post(
                f"{base_url}/auth/v1/admin/users",
                headers=admin_headers,
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"full_name": "Live Test User"},
                },
            )
            assert create_resp.status_code in (200, 201), (
                f"admin create_user failed: {create_resp.status_code} "
                f"{create_resp.text}"
            )
            supabase_user_id = create_resp.json()["id"]

            # 2. Sign in to obtain a real JWT.
            token_resp = await supa.post(
                f"{base_url}/auth/v1/token",
                params={"grant_type": "password"},
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Content-Type": "application/json",
                },
                json={"email": email, "password": password},
            )
            assert token_resp.status_code == 200, (
                f"sign-in failed: {token_resp.status_code} {token_resp.text}"
            )
            access_token = token_resp.json()["access_token"]

            # 3. Call our protected endpoint with the real JWT.
            me_resp = await http_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert me_resp.status_code == 200, (
                "auth/me rejected a real Supabase JWT. Most common causes: "
                "(1) project uses HS256 but SUPABASE_JWT_SECRET is unset, "
                "(2) project uses RS256 but SUPABASE_URL is wrong. "
                f"Response: {me_resp.status_code} {me_resp.text}"
            )
            data: dict[str, Any] = me_resp.json()
            assert data["email"] == email
            assert data["supabase_user_id"] == supabase_user_id
            assert data["name"] == "Live Test User"
            assert data["role"] == "owner"
        finally:
            # Always clean up — both sides.
            if supabase_user_id:
                async with httpx.AsyncClient(timeout=30.0) as cleanup:
                    await cleanup.delete(
                        f"{base_url}/auth/v1/admin/users/{supabase_user_id}",
                        headers=admin_headers,
                    )
                async with db.session() as s:
                    user = (
                        await s.execute(
                            select(User).where(
                                User.supabase_user_id == supabase_user_id
                            )
                        )
                    ).scalar_one_or_none()
                    if user is not None:
                        await s.execute(
                            delete(User).where(User.id == user.id)
                        )
                        await s.execute(
                            delete(Organization).where(
                                Organization.id == user.organization_id
                            )
                        )
                        await s.commit()
