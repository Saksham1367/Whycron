"""Billing-side persistence: the idempotency table for incoming Polar
webhooks (CONTEXT.md §7.4).

Polar guarantees at-least-once delivery — a single subscription change can
fire the same webhook event multiple times under retries or platform
restarts. We record every successfully-processed ``polar_event_id`` and
no-op subsequent deliveries of the same one.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base
from apps.api.models._mixins import CreatedAtMixin


class ProcessedPolarEvent(Base, CreatedAtMixin):
    __tablename__ = "processed_polar_events"

    # Polar's event ID is the primary key — uniqueness here is the
    # idempotency guarantee.
    polar_event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
