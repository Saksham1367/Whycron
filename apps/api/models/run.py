"""Event-sourced run records and their AI explanations.

Runs and AI explanations are append-only (CONTEXT.md §4.2.3). They have
``created_at`` only — never updated, never soft-deleted. State transitions
are computed from the event sequence; the row is the event.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base
from apps.api.models._mixins import CreatedAtMixin
from apps.api.uuid7 import uuid7


class Run(Base, CreatedAtMixin):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitors.id"),
        nullable=False,
    )

    # Optional user-provided ID for ping idempotency (CONTEXT.md §4.2.10).
    run_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 'started' | 'succeeded' | 'failed' | 'missed' | 'late' | 'timed_out'
    state: Mapped[str] = mapped_column(Text, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Last N lines, redacted before storage (CONTEXT.md §7.2).
    log_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Deterministic hash of (exit_code, last_10_log_lines_normalized).
    # Powers explanation dedup in V1 and the V3 pattern library.
    failure_signature_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # ``metadata`` is reserved on SQLAlchemy's DeclarativeBase, so the Python
    # attribute is renamed; the SQL column stays ``metadata`` per spec.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        Index("idx_runs_monitor_started", "monitor_id", "started_at"),
        Index("idx_runs_org_state", "organization_id", "state"),
        Index(
            "idx_runs_signature",
            "failure_signature_hash",
            postgresql_where=text("failure_signature_hash IS NOT NULL"),
        ),
        Index(
            "idx_runs_dedup",
            "monitor_id",
            "run_external_id",
            unique=True,
            postgresql_where=text("run_external_id IS NOT NULL"),
        ),
    )


class AIExplanation(Base, CreatedAtMixin):
    __tablename__ = "ai_explanations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("runs.id"),
        nullable=False,
    )

    # 'v1' | 'v2' — for prompt regression analysis (CONTEXT.md §8).
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # 'claude-haiku-4-5-20251001', etc.
    model: Mapped[str] = mapped_column(Text, nullable=False)

    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'low' | 'medium' | 'high'
    confidence: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="medium"
    )

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    # Microdollars (1e-6 USD). Avoids float drift across millions of rows.
    cost_usd_micro: Mapped[int] = mapped_column(Integer, nullable=False)

    # 'helpful' | 'not_helpful' | NULL
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # If this explanation was reused from another run with the same
    # signature hash (CONTEXT.md §8.3 dedup cache).
    cached_from_signature_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    __table_args__ = (Index("idx_explanations_run", "run_id"),)
