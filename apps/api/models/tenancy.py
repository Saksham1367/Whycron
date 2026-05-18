"""Multi-tenancy root: Organization and User.

CLAUDE.md rule 3: every other table filters by ``organization_id``. V1 has
one user per organization; V2 expands to teams without a schema change.
"""
from __future__ import annotations

import uuid
from typing import Any

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base
from apps.api.models._mixins import SoftDeleteMixin, TimestampMixin
from apps.api.uuid7 import uuid7


class Organization(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # 'free' | 'pro' | 'team' | 'business' | 'enterprise' — kept as TEXT (no
    # ENUM) so adding tiers does not require a migration.
    tier: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="free"
    )
    polar_customer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    polar_subscription_id: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    # Per-org feature flags (CONTEXT.md §4.2.7) — V1 has 3 flags, V3 will
    # have 30. Same code path, no schema change.
    features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Public status page (Phase 14). When set, ``GET /status/<slug>`` returns
    # an HTML page showing the org's public-flagged monitors. NULL means the
    # org has no status page configured. Globally unique so we can mount it
    # at a top-level path (and, later, at ``{slug}.status.whycron.com``).
    status_page_slug: Mapped[str | None] = mapped_column(
        Text, unique=True, nullable=True
    )
    # Optional headline shown above the monitor list on the public page.
    # Empty string is allowed (renders no headline). Limited to 200 chars
    # at the schema layer.
    status_page_headline: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    # Subject claim from Supabase Auth. Source of truth for identity; we
    # never trust JWT claims for org membership (CONTEXT.md §7.5).
    supabase_user_id: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'owner' | 'admin' | 'member'
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="owner"
    )

    # Terms-of-service acceptance audit trail (Phase 16). When NULL, the
    # dashboard shows a blocking modal until the user accepts. Updating
    # the published terms version invalidates prior acceptances — we
    # compare the stored ``terms_version_accepted`` against the current
    # ``settings.terms_version`` on every load.
    terms_version_accepted: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # IP address recorded at the moment of acceptance — legal proof if
    # an acceptance is later disputed. Truncated to 45 chars to fit IPv6.
    terms_accepted_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
