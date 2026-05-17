"""Reusable mapped-column mixins.

Every Whycron table follows the same lifecycle conventions (CONTEXT.md §5.2):

- ``TimestampMixin`` — every long-lived row carries ``created_at`` and
  ``updated_at`` as ``TIMESTAMPTZ`` with server-side defaults.
- ``SoftDeleteMixin`` — soft-delete only (CLAUDE.md rule 4). ``deleted_at``
  is nullable; queries must filter ``deleted_at IS NULL``.

Append-only event tables (``runs``, ``ai_explanations``,
``notification_deliveries``, ``audit_log``) deliberately do not use these —
they have ``created_at`` only and are never updated or soft-deleted.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CreatedAtMixin:
    """Append-only tables — no update, no soft delete."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
