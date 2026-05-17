"""Audit log — compliance and debugging.

CONTEXT.md §5.1 deliberately omits FKs on ``organization_id`` and
``user_id`` so the audit trail survives organization churn or user
deletion. Every mutation (CRUD, billing event, auth event) writes one row.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base
from apps.api.models._mixins import CreatedAtMixin
from apps.api.uuid7 import uuid7


class AuditLog(Base, CreatedAtMixin):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    # No FK — see module docstring.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # asyncpg returns ``ipaddress.IPv4Network``/``IPv6Network`` for INET on
    # SELECT; we store as string from request headers and let pg coerce.
    ip_address: Mapped[Any | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
