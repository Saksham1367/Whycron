"""Auth-related routes + the FastAPI dependency that protects others.

``get_current_user`` is the single auth boundary. Every protected route in
later phases depends on it. It accepts either of two credentials:

1. ``Authorization: Bearer <Supabase JWT>`` — the dashboard.
2. ``X-Whycron-API-Key: wcr_live_...`` — programmatic clients (Phase 11).

Whichever credential is present, the function returns an
:class:`AuthedUser` value with the resolved Whycron identity and the
authentication metadata routes need for scope enforcement.

Any failure step raises ``HTTPException(401)`` with a ``WWW-Authenticate``
header so frontends can re-prompt for sign-in.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from apps.api.db import db
from apps.api.services.api_keys import (
    has_required_scope,
    lookup_and_verify,
)
from apps.api.services.auth import (
    AuthedUser,
    AuthError,
    _claims_to_user_fields,
    load_or_create_user,
    verify_supabase_jwt,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _unauthorized(detail: str, scheme: str = "Bearer") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": scheme},
    )


async def _authenticate_jwt(token: str) -> AuthedUser:
    try:
        claims = verify_supabase_jwt(token)
        supabase_user_id, email, name = _claims_to_user_fields(claims)
    except AuthError as exc:
        raise _unauthorized(str(exc)) from exc

    async with db.session() as session:
        return await load_or_create_user(
            session,
            supabase_user_id=supabase_user_id,
            email=email,
            name=name,
        )


async def _authenticate_api_key(plaintext: str) -> AuthedUser:
    async with db.session() as session:
        result = await lookup_and_verify(session, plaintext=plaintext)
        if result is None:
            raise _unauthorized("Invalid or revoked API key", scheme="ApiKey")
        key, user, _org = result
        return AuthedUser(
            id=user.id,
            organization_id=user.organization_id,
            supabase_user_id=user.supabase_user_id,
            email=user.email,
            name=user.name,
            role=user.role,
            auth_method="api_key",
            scopes=tuple(key.scopes or ()),
            api_key_id=key.id,
        )


async def get_current_user(
    authorization: str | None = Header(None),
    x_whycron_api_key: str | None = Header(None),
) -> AuthedUser:
    """FastAPI dependency: returns the authenticated Whycron user.

    Accepts either a Supabase JWT (``Authorization: Bearer ...``) or a
    Whycron API key (``X-Whycron-API-Key: wcr_live_...``). If both are
    sent, the JWT wins — the dashboard is the higher-trust path and
    presenting both usually indicates a misconfigured client.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise _unauthorized("Empty bearer token")
        return await _authenticate_jwt(token)

    if x_whycron_api_key:
        return await _authenticate_api_key(x_whycron_api_key.strip())

    raise _unauthorized(
        "Provide either Authorization: Bearer <jwt> or X-Whycron-API-Key"
    )


def require_scope(*needed: str):
    """Build a FastAPI dependency that enforces a scope requirement.

    JWT-authenticated callers always pass (the dashboard owner has the
    full set implicitly). API-key callers pass iff their granted scope
    list satisfies the ``needed`` set — see
    :func:`apps.api.services.api_keys.has_required_scope`.

    Usage::

        @router.post("/monitors", dependencies=[Depends(require_scope("monitors:write"))])
    """
    needed_tuple = tuple(needed)

    async def _dep(auth: AuthedUser = Depends(get_current_user)) -> AuthedUser:
        if has_required_scope(auth.scopes, needed_tuple):
            return auth
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "API key is missing required scope. Needed one of: "
                + ", ".join(needed_tuple)
            ),
        )

    return _dep


@router.get("/me")
async def me(auth: AuthedUser = Depends(get_current_user)) -> dict[str, Any]:
    """Returns the authenticated user + their Whycron org."""
    return {
        "user_id": str(auth.id),
        "organization_id": str(auth.organization_id),
        "supabase_user_id": auth.supabase_user_id,
        "email": auth.email,
        "name": auth.name,
        "role": auth.role,
        "auth_method": auth.auth_method,
        "scopes": list(auth.scopes) if auth.scopes is not None else None,
    }
