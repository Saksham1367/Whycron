"""Notification channels (where alerts go) and delivery history.

``NotificationChannel.config`` is encrypted at rest for fields that contain
user secrets (webhook signing keys, Slack tokens) per CONTEXT.md §7.7.
The encryption layer lands in Phase 6 (alert dispatcher).

``NotificationDelivery`` is append-only — once a delivery attempt is logged
it is not mutated; retries create new deliveries.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base
from apps.api.models._mixins import (
    CreatedAtMixin,
    SoftDeleteMixin,
    TimestampMixin,
)
from apps.api.uuid7 import uuid7


class NotificationChannel(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    # 'email' | 'webhook' | 'slack' | 'discord'
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Encrypted-at-rest fields live inside this JSONB.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class NotificationDelivery(Base, CreatedAtMixin):
    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    # No FK on organization_id by design (mirrors CONTEXT.md §5.1) — delivery
    # records survive org churn for debugging and audit.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("runs.id"),
        nullable=True,
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("notification_channels.id"),
        nullable=True,
    )
    channel_type: Mapped[str] = mapped_column(Text, nullable=False)

    # 'pending' | 'sent' | 'failed' | 'retrying'
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Summary for debugging — never the full payload (avoids leaking secrets
    # back through delivery logs).
    payload_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Channel-specific reference returned by the destination. For Slack:
    # the message ``ts`` (used as ``thread_ts`` for subsequent replies on
    # the same incident). For Discord / webhook: not used today.
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
