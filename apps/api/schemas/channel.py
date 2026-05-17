"""Notification channel schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

ChannelType = Literal["email", "webhook", "slack", "discord"]


class ChannelCreate(BaseModel):
    type: ChannelType
    name: str = Field(..., min_length=1, max_length=120)
    config: dict[str, Any]
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_config(self) -> "ChannelCreate":
        if self.type == "email":
            to = self.config.get("to")
            if not to or "@" not in str(to):
                raise ValueError(
                    "email channel requires config.to with a valid address"
                )
        elif self.type in ("webhook", "discord"):
            url = self.config.get("url")
            if not url or not str(url).startswith("https://"):
                raise ValueError(
                    f"{self.type} channel requires config.url starting with https://"
                )
        elif self.type == "slack":
            # Slack OAuth is a V2 feature; reject for V1 cleanly.
            raise ValueError("slack channel is not yet supported")
        return self


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    name: str
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
