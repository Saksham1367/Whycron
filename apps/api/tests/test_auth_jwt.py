"""JWT verifier unit tests.

All tests here use HS256 with a monkeypatched secret — deterministic, no
network, no Supabase project required. The live RS256 round-trip lives in
``test_auth_live_supabase.py``.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import jwt as pyjwt
import pytest

from apps.api.services.auth import AuthError, verify_supabase_jwt

TEST_SECRET = "test-secret-do-not-use-in-production-32-chars-of-padding"


def _make_token(secret: str = TEST_SECRET, **claim_overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
        "email": "test@example.com",
        "user_metadata": {"full_name": "Test User"},
    }
    claims.update(claim_overrides)
    return pyjwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def hs256_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.api.config.settings.supabase_jwt_secret", TEST_SECRET
    )


def test_verifies_a_well_formed_token(hs256_secret: None) -> None:
    claims = verify_supabase_jwt(_make_token())
    assert claims["aud"] == "authenticated"
    assert claims["email"] == "test@example.com"


def test_rejects_garbage_input(hs256_secret: None) -> None:
    with pytest.raises(AuthError):
        verify_supabase_jwt("not.a.valid.jwt")


def test_rejects_wrong_signature(hs256_secret: None) -> None:
    forged = _make_token(
        secret="some-other-secret-entirely-with-extra-padding-bytes-here"
    )
    with pytest.raises(AuthError, match="verification failed"):
        verify_supabase_jwt(forged)


def test_rejects_expired_token(hs256_secret: None) -> None:
    expired = _make_token(exp=int(time.time()) - 60)
    with pytest.raises(AuthError, match="verification failed"):
        verify_supabase_jwt(expired)


def test_rejects_wrong_audience(hs256_secret: None) -> None:
    """Service-role tokens have ``aud='service_role'`` — never accept them
    as user authentication."""
    bad = _make_token(aud="service_role")
    with pytest.raises(AuthError, match="verification failed"):
        verify_supabase_jwt(bad)


def test_rejects_token_missing_sub(hs256_secret: None) -> None:
    # We can't just pop 'sub' from _make_token because PyJWT requires it
    # in the encode path; build a payload manually.
    now = int(time.time())
    token = pyjwt.encode(
        {
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
            "email": "x@y.com",
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        verify_supabase_jwt(token)


def test_rejects_token_missing_exp(hs256_secret: None) -> None:
    token = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "email": "x@y.com",
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        verify_supabase_jwt(token)


def test_rejects_hs256_when_secret_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the project sends HS256 but we never set SUPABASE_JWT_SECRET,
    we should surface a clear error instead of silently passing."""
    monkeypatch.setattr("apps.api.config.settings.supabase_jwt_secret", "")
    with pytest.raises(AuthError, match="SUPABASE_JWT_SECRET"):
        verify_supabase_jwt(_make_token())


def test_rejects_unsupported_algorithm() -> None:
    """``alg=none`` and other non-HS256/RS256 algs must be refused."""
    # Manually craft a JWT-like string with alg=none (no real PyJWT helper
    # produces this without options.verify_signature=False on decode).
    import base64
    import json

    def b64(d):
        return (
            base64.urlsafe_b64encode(json.dumps(d).encode())
            .rstrip(b"=")
            .decode()
        )

    header = {"alg": "none", "typ": "JWT"}
    payload = {"sub": "x", "aud": "authenticated", "exp": int(time.time()) + 60}
    token = f"{b64(header)}.{b64(payload)}."

    with pytest.raises(AuthError, match="unsupported"):
        verify_supabase_jwt(token)
