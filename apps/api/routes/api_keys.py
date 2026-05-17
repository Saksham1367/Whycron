"""API-key management endpoints.

These three routes manage the keys themselves. They require ``admin``
scope, which means: only the dashboard (JWT auth) and previously-issued
admin keys can mint, list, or revoke. A monitors-only key cannot bootstrap
new credentials.

Creating a key is the only place the plaintext value is ever returned by
the API. List / get returns the prefix and metadata, never the full
value or the bcrypt hash.
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from apps.api.db import db
from apps.api.models import APIKey
from apps.api.routes.auth import require_scope
from apps.api.schemas.api_key import APIKeyCreate, APIKeyCreateOut, APIKeyOut
from apps.api.services import api_keys as api_keys_service
from apps.api.services.auth import AuthedUser

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])
log = structlog.get_logger("whycron.api.api_keys")


@router.post("", response_model=APIKeyCreateOut, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: APIKeyCreate,
    auth: AuthedUser = Depends(require_scope("admin")),
) -> dict[str, Any]:
    if not api_keys_service.validate_scopes(list(payload.scopes)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one valid scope is required",
        )

    async with db.session() as session:
        row, plaintext = await api_keys_service.create_api_key(
            session,
            organization_id=auth.organization_id,
            user_id=auth.id,
            name=payload.name,
            scopes=list(payload.scopes),
            expires_at=payload.expires_at,
        )

    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "scopes": list(row.scopes or []),
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "plaintext": plaintext,
    }


@router.get("", response_model=list[APIKeyOut])
async def list_api_keys(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> list[APIKey]:
    async with db.session() as session:
        rows = (
            await session.execute(
                select(APIKey)
                .where(APIKey.organization_id == auth.organization_id)
                .order_by(APIKey.created_at.desc())
            )
        ).scalars().all()
    return list(rows)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    auth: AuthedUser = Depends(require_scope("admin")),
) -> None:
    async with db.session() as session:
        row = await api_keys_service.revoke_api_key(
            session,
            organization_id=auth.organization_id,
            key_id=key_id,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
