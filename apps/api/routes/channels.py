"""Notification channels CRUD.

Each channel routes alerts to one transport (email/webhook/discord). On
create + update we run the SSRF guard against any URL field so users
cannot point us at their own internal infrastructure. The ``config`` blob
is JSONB; secret fields inside it (e.g. webhook signing secret) are
intended to be encrypted at rest in a later phase — for now they're
stored as-is and redacted from list/get responses.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import db
from apps.api.models import AuditLog, NotificationChannel
from apps.api.routes.auth import get_current_user
from apps.api.schemas.channel import (
    ChannelCreate,
    ChannelOut,
    ChannelUpdate,
)
from apps.api.services.auth import AuthedUser
from apps.api.services.notify.ssrf import (
    UnsafeWebhookURL,
    validate_webhook_url,
)

router = APIRouter(
    prefix="/api/v1/notification-channels", tags=["channels"]
)
log = structlog.get_logger("whycron.api.channels")


def _sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Mask secret-y fields before sending a channel back to the user."""
    if not config:
        return {}
    sanitized = dict(config)
    for key in ("secret", "signing_secret", "token"):
        if key in sanitized and sanitized[key]:
            sanitized[key] = "***"
    return sanitized


def _validate_url_if_present(channel_type: str, config: dict[str, Any]) -> None:
    if channel_type in ("webhook", "discord"):
        url = config.get("url")
        if not url:
            return
        try:
            validate_webhook_url(url)
        except UnsafeWebhookURL as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsafe URL: {exc}",
            ) from exc


async def _load_channel_or_404(
    session: AsyncSession, channel_id: uuid.UUID, org_id: uuid.UUID
) -> NotificationChannel:
    channel = (
        await session.execute(
            select(NotificationChannel).where(
                NotificationChannel.id == channel_id,
                NotificationChannel.organization_id == org_id,
                NotificationChannel.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification channel not found",
        )
    return channel


def _audit(
    *,
    auth: AuthedUser,
    request: Request,
    action: str,
    entity_id: uuid.UUID,
    diff: dict[str, Any] | None = None,
) -> AuditLog:
    return AuditLog(
        organization_id=auth.organization_id,
        user_id=auth.id,
        action=action,
        entity_type="notification_channel",
        entity_id=entity_id,
        diff=diff,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent", "") or None)[:500]
        if request.headers.get("user-agent")
        else None,
    )


def _to_out(channel: NotificationChannel, *, reveal_config: bool) -> ChannelOut:
    data = ChannelOut.model_validate(channel)
    if not reveal_config:
        data = data.model_copy(update={"config": _sanitize_config(channel.config)})
    return data


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=dict[str, Any])
async def list_channels(
    auth: AuthedUser = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    async with db.session() as session:
        base = select(NotificationChannel).where(
            NotificationChannel.organization_id == auth.organization_id,
            NotificationChannel.deleted_at.is_(None),
        )
        total = (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        items = (
            await session.execute(
                base.order_by(NotificationChannel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
    return {
        "items": [
            _to_out(c, reveal_config=False).model_dump(mode="json")
            for c in items
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "",
    response_model=ChannelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    body: ChannelCreate,
    request: Request,
    auth: AuthedUser = Depends(get_current_user),
) -> ChannelOut:
    _validate_url_if_present(body.type, body.config)

    async with db.session() as session:
        channel = NotificationChannel(
            organization_id=auth.organization_id,
            type=body.type,
            name=body.name,
            config=body.config,
            enabled=body.enabled,
        )
        session.add(channel)
        await session.flush()
        session.add(
            _audit(
                auth=auth,
                request=request,
                action="channel.create",
                entity_id=channel.id,
                diff={"after": {"type": body.type, "name": body.name}},
            )
        )
        await session.commit()
        # Reveal the config on create only (so the user can copy out any
        # secret they configured). Subsequent reads sanitize.
        return _to_out(channel, reveal_config=True)


@router.get("/{channel_id}", response_model=ChannelOut)
async def get_channel(
    channel_id: uuid.UUID,
    auth: AuthedUser = Depends(get_current_user),
) -> ChannelOut:
    async with db.session() as session:
        channel = await _load_channel_or_404(
            session, channel_id, auth.organization_id
        )
    return _to_out(channel, reveal_config=False)


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelUpdate,
    request: Request,
    auth: AuthedUser = Depends(get_current_user),
) -> ChannelOut:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields supplied",
        )

    async with db.session() as session:
        channel = await _load_channel_or_404(
            session, channel_id, auth.organization_id
        )
        if "config" in updates:
            _validate_url_if_present(channel.type, updates["config"])

        for field, value in updates.items():
            setattr(channel, field, value)
        await session.flush()
        session.add(
            _audit(
                auth=auth,
                request=request,
                action="channel.update",
                entity_id=channel.id,
                diff={"after": updates},
            )
        )
        await session.commit()
        # Refresh inside the session block so the fresh ``updated_at``
        # (set by server-side ``onupdate=func.now()``) is populated before
        # we leave the context manager and the instance becomes detached.
        await session.refresh(channel)
        return _to_out(channel, reveal_config=False)


@router.delete(
    "/{channel_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_channel(
    channel_id: uuid.UUID,
    request: Request,
    auth: AuthedUser = Depends(get_current_user),
) -> None:
    async with db.session() as session:
        channel = await _load_channel_or_404(
            session, channel_id, auth.organization_id
        )
        channel.deleted_at = datetime.now(timezone.utc)
        session.add(
            _audit(
                auth=auth,
                request=request,
                action="channel.delete",
                entity_id=channel.id,
            )
        )
        await session.commit()
