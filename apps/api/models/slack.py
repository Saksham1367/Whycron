"""Slack workspace installation, one per org.

When a user connects their Slack workspace via OAuth (Phase 13), we
persist the resulting bot token plus identifying metadata here. Bot
tokens are encrypted at rest via :func:`apps.api.services.crypto.encrypt`
— what hits the column is the ciphertext, never the raw value.

A workspace can later be disconnected by the user; we set ``deleted_at``
and treat the row as gone (consistent with CONTEXT.md rule 4 — soft
delete only).
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base
from apps.api.models._mixins import SoftDeleteMixin, TimestampMixin
from apps.api.uuid7 import uuid7


class SlackInstallation(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "slack_installations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        unique=True,  # one Slack workspace per Whycron org
    )

    # Slack workspace identifiers (returned by oauth.v2.access).
    team_id: Mapped[str] = mapped_column(Text, nullable=False)
    team_name: Mapped[str] = mapped_column(Text, nullable=False)

    # The bot user inside Slack. Used as the message author.
    bot_user_id: Mapped[str] = mapped_column(Text, nullable=False)

    # Bot token. Encrypted with Fernet via apps.api.services.crypto. Never the
    # raw ``xoxb-...`` string.
    bot_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Comma-separated list of scopes granted by the user during OAuth. Useful
    # for diagnosing failures ("you didn't grant chat:write so we can't post").
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # The Slack app's own id, returned by oauth.v2.access. Useful if we ever
    # rotate the Whycron-side Slack App.
    app_id: Mapped[str] = mapped_column(Text, nullable=False)

    # Slack user who authorized the install. Lets us tell the team
    # "installed by alice@..." in the dashboard.
    authed_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
