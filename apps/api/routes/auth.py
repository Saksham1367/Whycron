"""Auth-related routes + the FastAPI dependency that protects others.

``get_current_user`` is the single auth boundary. Every protected route in
later phases depends on it. It does three things:

1. Pulls the bearer token from the ``Authorization`` header.
2. Verifies the Supabase JWT (HS256 or RS256, see ``services.auth``).
3. Resolves or creates the Whycron user record, returning an
   :class:`AuthedUser` value object the route handler can use.

Any failure step raises ``HTTPException(401)`` with a ``WWW-Authenticate``
header so frontends can re-prompt for sign-in.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from apps.api.db import db
from apps.api.services.auth import (
    AuthedUser,
    AuthError,
    _claims_to_user_fields,
    load_or_create_user,
    verify_supabase_jwt,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def get_current_user(
    authorization: str | None = Header(None),
) -> AuthedUser:
    """FastAPI dependency: returns the authenticated Whycron user.

    Used as ``auth: AuthedUser = Depends(get_current_user)`` on protected
    routes. Raises 401 for missing, malformed, expired, or otherwise
    invalid tokens.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = verify_supabase_jwt(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        supabase_user_id, email, name = _claims_to_user_fields(claims)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    async with db.session() as session:
        return await load_or_create_user(
            session,
            supabase_user_id=supabase_user_id,
            email=email,
            name=name,
        )


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
    }
