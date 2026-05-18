"""Account / org schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UsageBlock(BaseModel):
    monitors_active: int
    monitors_limit: int  # ``-1`` means unlimited
    ai_explanations_this_month: int
    ai_explanations_monthly_limit: int  # ``-1`` means unlimited


class DeploymentFlags(BaseModel):
    """Runtime flags the frontend needs to gate UI on. Returned with every
    ``/api/v1/account`` response so the dashboard adapts to the deployment
    type without an extra round-trip."""

    self_host_mode: bool
    ai_enabled: bool
    slack_oauth_enabled: bool
    billing_enabled: bool


class AccountOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    tier: str
    features: dict[str, Any]
    user_id: uuid.UUID
    email: str
    name: str | None
    role: str
    usage: UsageBlock
    created_at: datetime
    deployment: DeploymentFlags
