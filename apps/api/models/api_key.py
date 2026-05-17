"""API keys for programmatic monitor management (V2 feature).

The table exists from V1 so the schema is stable. Key plaintext is never
stored — only a bcrypt hash and a short prefix for UI display
(CONTEXT.md §7.6). Rotation uses ``revoked_at`` rather than soft delete:
revoked rows stay queryable for audit.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime

from apps.api.db import Base
from apps.api.models._mixins import CreatedAtMixin
from apps.api.uuid7 import uuid7


class APIKey(Base, CreatedAtMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # bcrypt hash (cost factor 12) of the full key. Never the plaintext.
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # First 8 chars of the plaintext, e.g. ``wcr_live_a8f3``. UI display only.
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    # 'monitors:read' | 'monitors:write' | 'runs:read' | 'admin'
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
