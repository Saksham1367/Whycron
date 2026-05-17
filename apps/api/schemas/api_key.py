"""API key request + response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Scope = Literal["monitors:read", "monitors:write", "runs:read", "admin"]


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: list[Scope] = Field(default_factory=list, min_length=1)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def _expires_in_future(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return v


class APIKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class APIKeyCreateOut(APIKeyOut):
    """Returned **only** from the create endpoint, on the response that
    mints the key. Carries the plaintext so the caller can copy it once.
    """

    plaintext: str = Field(
        description=(
            "Full API key value. Shown only here — Whycron does not store the "
            "plaintext and cannot recover it later. Treat this as a secret."
        )
    )
