"""Supabase JWT verification + first-signin flow (CONTEXT.md §7.5).

We never re-implement password hashing or session tokens — Supabase Auth
issues the JWTs, we just verify them. Two signing algorithms are supported
because Supabase projects can be configured either way:

- **HS256** (legacy default): shared secret in ``SUPABASE_JWT_SECRET``,
  found in the Supabase dashboard → Settings → API → JWT Secret.
- **RS256** (new default): verified via the project's JWKS endpoint at
  ``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``. ``PyJWKClient`` caches
  the keys in-process between requests.

Per §7.5: we never trust JWT claims for organization membership. The JWT
identifies *who* the user is (via ``sub`` = supabase_user_id); the Whycron
``users`` table is the source of truth for which org they belong to. On
first sign-in we create both an Organization and a User row for them.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
import structlog
from jwt import InvalidTokenError, PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models import Organization, User

log = structlog.get_logger("whycron.auth")


class AuthError(Exception):
    """Anything that should be surfaced as a 401 to the caller."""


@dataclass(frozen=True)
class AuthedUser:
    """Resolved Whycron identity for a verified Supabase JWT."""

    id: uuid.UUID
    organization_id: uuid.UUID
    supabase_user_id: str
    email: str
    name: str | None
    role: str


# ── JWT verification ─────────────────────────────────────────────────────────


# Asymmetric signing algorithms we verify via JWKS. Supabase's "JWT Signing
# Keys" feature can rotate between any of these depending on the current
# key type (ECC P-256 → ES256, RSA → RS256, Ed25519 → EdDSA).
_ASYMMETRIC_ALGS = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"}
)

_JWKS_CLIENT: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _JWKS_CLIENT
    if _JWKS_CLIENT is None:
        if not settings.supabase_url:
            raise AuthError("SUPABASE_URL is not configured")
        url = (
            settings.supabase_url.rstrip("/")
            + "/auth/v1/.well-known/jwks.json"
        )
        _JWKS_CLIENT = PyJWKClient(url, cache_keys=True, lifespan=300)
    return _JWKS_CLIENT


def _reset_jwks_client() -> None:
    """Test hook — drops the cached JWKS client. Not used in prod."""
    global _JWKS_CLIENT
    _JWKS_CLIENT = None


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify signature, expiry, and audience. Returns the decoded claims.

    Raises ``AuthError`` for any verification failure. Callers turn that
    into a 401 response.
    """
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise AuthError(f"malformed JWT header: {exc}") from exc

    alg = header.get("alg")
    # 30s leeway absorbs ordinary clock skew between Supabase and our host.
    # PyJWT defaults to 0, which is stricter than most JWT libraries — it
    # rejects tokens whose ``iat`` is even a fraction of a second in the
    # future. ``exp`` validation still rejects truly stale tokens within
    # the same 30s envelope.
    decode_kwargs: dict[str, Any] = {
        "audience": "authenticated",
        "leeway": 30,
        "options": {"require": ["exp", "sub"]},
    }

    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise AuthError(
                "received an HS256 JWT but SUPABASE_JWT_SECRET is not "
                "configured — add it from Supabase dashboard → Settings → "
                "API → JWT Secret, or use a project with RS256 signing"
            )
        try:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                **decode_kwargs,
            )
        except InvalidTokenError as exc:
            raise AuthError(f"JWT verification failed: {exc}") from exc

    # Asymmetric algorithms — verified via the project's JWKS endpoint.
    # Supabase's "JWT Signing Keys" feature can issue any of these depending
    # on the current key type (ECC P-256 → ES256, RSA → RS256, Ed25519 →
    # EdDSA). PyJWT handles all of them once it has the public key.
    if alg in _ASYMMETRIC_ALGS:
        try:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                **decode_kwargs,
            )
        except InvalidTokenError as exc:
            raise AuthError(f"JWT verification failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 — JWKS network or parsing errors
            raise AuthError(f"JWKS lookup failed: {exc}") from exc

    raise AuthError(f"unsupported JWT algorithm: {alg!r}")


# ── First-signin user + org creation ─────────────────────────────────────────


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _email_to_slug(email: str) -> str:
    base = _SLUG_RE.sub("-", email.lower().split("@")[0]).strip("-") or "user"
    # 6 hex chars of randomness keeps the slug unique even if two people
    # named alice@... sign up.
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _claims_to_user_fields(
    claims: dict[str, Any],
) -> tuple[str, str, str | None]:
    """Pull (supabase_user_id, email, name) out of the verified claims."""
    sub = claims.get("sub")
    if not sub:
        raise AuthError("JWT missing 'sub' claim")

    email = claims.get("email")
    user_metadata = claims.get("user_metadata") or {}
    if not email:
        email = user_metadata.get("email")
    if not email:
        raise AuthError("JWT missing email claim")

    name = (
        user_metadata.get("full_name")
        or user_metadata.get("name")
        or None
    )
    return sub, email, name


async def load_or_create_user(
    session: AsyncSession,
    *,
    supabase_user_id: str,
    email: str,
    name: str | None,
) -> AuthedUser:
    """Resolve the Whycron user for this Supabase identity.

    First call: creates an ``Organization`` + ``User`` atomically and
    returns the new identity. Subsequent calls: returns the existing row
    without modification.
    """
    existing = (
        await session.execute(
            select(User).where(
                User.supabase_user_id == supabase_user_id,
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        return AuthedUser(
            id=existing.id,
            organization_id=existing.organization_id,
            supabase_user_id=existing.supabase_user_id,
            email=existing.email,
            name=existing.name,
            role=existing.role,
        )

    workspace_owner = name or email.split("@", 1)[0]
    org = Organization(
        name=f"{workspace_owner}'s workspace",
        slug=_email_to_slug(email),
    )
    session.add(org)
    await session.flush()

    user = User(
        organization_id=org.id,
        supabase_user_id=supabase_user_id,
        email=email,
        name=name,
        role="owner",
    )
    session.add(user)
    await session.commit()

    log.info(
        "first_signin_user_created",
        user_id=str(user.id),
        org_id=str(org.id),
        email=email,
    )

    return AuthedUser(
        id=user.id,
        organization_id=org.id,
        supabase_user_id=supabase_user_id,
        email=email,
        name=name,
        role="owner",
    )
