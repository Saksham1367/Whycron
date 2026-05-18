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


class TermsState(BaseModel):
    """Per-user terms-of-service acceptance state.

    ``current_version`` is the published terms version. ``accepted_version``
    is whatever the user last accepted (NULL if never). ``is_up_to_date``
    is True iff the two strings match — the frontend uses this single
    boolean to decide whether to show the acceptance modal.
    """

    current_version: str
    accepted_version: str | None
    accepted_at: datetime | None
    is_up_to_date: bool


class TermsAcceptIn(BaseModel):
    """Body for POST /api/v1/account/accept-terms.

    The version the user is accepting is sent explicitly so a stale
    dashboard can't auto-accept a newer version the user never saw.
    The backend rejects if the value doesn't match ``settings.terms_version``.
    """

    version: str


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
    terms: TermsState
