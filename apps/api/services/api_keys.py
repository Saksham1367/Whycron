"""Programmatic API keys — generate, verify, revoke.

Format: ``wcr_live_<43 url-safe base64 chars>``. 32 random bytes = 256
bits of entropy; far stronger than any password. We bcrypt-hash the
plaintext at cost 12 anyway, per ROADMAP, as defense in depth.

Plaintext is shown to the user exactly **once** at creation. Subsequent
reads return only the prefix (first 13 chars, e.g. ``wcr_live_a8f3``)
and metadata — never the hash or the plaintext.

Revocation is soft: ``revoked_at`` is set, the row stays for audit.
Verification rejects revoked keys, expired keys, and keys for orgs
that have been soft-deleted.

Scopes are stored as a Postgres ``text[]``. The four V2 scopes are:

- ``monitors:read``  — list monitors, fetch a single monitor + runs
- ``monitors:write`` — create / update / delete monitors and channels
- ``runs:read``      — list runs and fetch run detail
- ``admin``          — implies all of the above plus account/billing/keys

JWT auth (the dashboard) is implicitly admin-equivalent — see
``apps/api/routes/auth.py``.
"""
from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import datetime, timezone
from typing import Final

import bcrypt
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import APIKey, Organization, User

log = structlog.get_logger("whycron.api_keys")

KEY_PLAINTEXT_PREFIX: Final[str] = "wcr_live_"
KEY_RANDOM_BYTES: Final[int] = 32
KEY_DISPLAY_PREFIX_LENGTH: Final[int] = 13  # "wcr_live_" + 4 chars
BCRYPT_COST: Final[int] = 12

VALID_SCOPES: Final[frozenset[str]] = frozenset(
    {"monitors:read", "monitors:write", "runs:read", "admin"}
)


def generate_key_plaintext() -> str:
    """Mint a fresh API key plaintext. Shown to the user once."""
    return KEY_PLAINTEXT_PREFIX + secrets.token_urlsafe(KEY_RANDOM_BYTES)


def display_prefix(plaintext: str) -> str:
    return plaintext[:KEY_DISPLAY_PREFIX_LENGTH]


def _hash_sync(plaintext: str) -> str:
    return bcrypt.hashpw(
        plaintext.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_COST)
    ).decode("utf-8")


async def hash_key(plaintext: str) -> str:
    """Bcrypt-hash a plaintext key. Async-threaded — ~200ms of CPU work."""
    return await asyncio.to_thread(_hash_sync, plaintext)


def _verify_sync(plaintext: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash on disk — treat as no match, never crash a request.
        return False


async def verify_key(plaintext: str, hashed: str) -> bool:
    return await asyncio.to_thread(_verify_sync, plaintext, hashed)


def validate_scopes(scopes: list[str]) -> list[str]:
    """Filter to the known scope set and de-duplicate, preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for s in scopes:
        if s in VALID_SCOPES and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def has_required_scope(granted: tuple[str, ...] | None, needed: tuple[str, ...]) -> bool:
    """Return True iff the granted scopes satisfy the needed set.

    ``None`` granted means the caller authed via JWT — always allowed.
    ``admin`` in granted satisfies any non-empty needed list.
    Empty ``needed`` is always satisfied.
    """
    if granted is None:
        return True
    if not needed:
        return True
    if "admin" in granted:
        return True
    return any(n in granted for n in needed)


async def lookup_and_verify(
    session: AsyncSession, *, plaintext: str
) -> tuple[APIKey, User, Organization] | None:
    """Resolve an API key plaintext to (key, user, org).

    Returns ``None`` for unknown / revoked / expired keys, or keys whose
    org or user have been soft-deleted. On success, updates
    ``last_used_at`` to now and flushes the session.
    """
    if not plaintext or not plaintext.startswith(KEY_PLAINTEXT_PREFIX):
        return None

    prefix = display_prefix(plaintext)

    # Narrow by prefix first to avoid bcrypt-verifying every key in the table.
    # The prefix has ~24 bits of randomness which is plenty for a per-key
    # lookup index without leaking key material.
    candidates = (
        await session.execute(
            select(APIKey).where(
                APIKey.key_prefix == prefix,
                APIKey.revoked_at.is_(None),
            )
        )
    ).scalars().all()

    if not candidates:
        return None

    now = datetime.now(timezone.utc)

    for candidate in candidates:
        if candidate.expires_at is not None and candidate.expires_at <= now:
            continue
        if not await verify_key(plaintext, candidate.key_hash):
            continue

        # Resolve the User and Organization. Either being soft-deleted
        # invalidates the key.
        user = (
            await session.execute(
                select(User).where(
                    User.id == candidate.user_id,
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if user is None:
            return None
        org = (
            await session.execute(
                select(Organization).where(
                    Organization.id == candidate.organization_id,
                    Organization.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if org is None:
            return None

        candidate.last_used_at = now
        # Commit so the timestamp persists past the auth context's session.
        # ``flush`` alone would be rolled back when the session closes.
        await session.commit()
        return candidate, user, org

    return None


async def create_api_key(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[APIKey, str]:
    """Mint a new key. Returns (row, plaintext). Plaintext is shown to the
    caller once — we never store it.
    """
    clean_scopes = validate_scopes(scopes)
    plaintext = generate_key_plaintext()
    prefix = display_prefix(plaintext)
    key_hash = await hash_key(plaintext)

    row = APIKey(
        organization_id=organization_id,
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=clean_scopes,
        expires_at=expires_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    log.info(
        "api_key_created",
        org_id=str(organization_id),
        user_id=str(user_id),
        key_id=str(row.id),
        scopes=clean_scopes,
    )
    return row, plaintext


async def revoke_api_key(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    key_id: uuid.UUID,
) -> APIKey | None:
    """Soft-revoke a key. Idempotent: revoking an already-revoked key is a
    no-op that returns the same row. Cross-org access returns ``None``.
    """
    row = (
        await session.execute(
            select(APIKey).where(
                APIKey.id == key_id,
                APIKey.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()
        log.info(
            "api_key_revoked",
            org_id=str(organization_id),
            key_id=str(key_id),
        )
    return row
