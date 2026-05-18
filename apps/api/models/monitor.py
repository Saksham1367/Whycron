"""Monitor — a registered cron job / scheduled task being watched.

The ``ping_token`` is the public secret embedded in the URL the user's job
hits. It is unique forever (CONTEXT.md §4.2.2 — backward compatibility on
``/p/{ping_token}``).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base
from apps.api.models._mixins import SoftDeleteMixin, TimestampMixin
from apps.api.uuid7 import uuid7


class Monitor(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "monitors"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Public per-monitor secret embedded in /p/{ping_token}. Must remain
    # unique and stable for the lifetime of the monitor.
    ping_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    # 'cron' | 'interval' | 'on_demand'
    schedule_type: Mapped[str] = mapped_column(Text, nullable=False)
    # cron expression "0 2 * * *", or interval seconds "300", or "" for on_demand
    schedule_value: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="UTC"
    )

    grace_period_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="60"
    )
    # If set, runs that exceed this without an end-ping are flagged 'stuck'.
    expected_runtime_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # 'healthy' | 'failing' | 'late' | 'paused' | 'unknown'
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="unknown"
    )
    paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # When true, this monitor surfaces on the org's public status page
    # (Phase 14). Default is private; users opt monitors in one by one.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )
    notification_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        # Active-monitor lookups by status, scoped to org.
        Index(
            "idx_monitors_org_status",
            "organization_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Active-monitor lookup by ping token (the column UNIQUE is global,
        # this partial index makes the hot-path lookup fast).
        Index(
            "idx_monitors_ping_token",
            "ping_token",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
