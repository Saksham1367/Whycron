"""Monitor request + response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator

ScheduleType = Literal["cron", "interval", "on_demand"]
MonitorStatus = Literal["healthy", "failing", "late", "paused", "unknown"]


class MonitorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    schedule_type: ScheduleType
    schedule_value: str = Field(..., max_length=500)
    timezone: str = Field(default="UTC", max_length=50)
    grace_period_seconds: int = Field(default=60, ge=0, le=86_400)
    expected_runtime_seconds: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notification_settings: dict[str, object] = Field(default_factory=dict)

    @field_validator("schedule_value")
    @classmethod
    def _validate_schedule(cls, v: str, info) -> str:  # type: ignore[no-untyped-def]
        schedule_type = info.data.get("schedule_type")
        if schedule_type == "cron":
            try:
                croniter(v)
            except Exception as exc:
                raise ValueError(f"invalid cron expression: {exc}") from exc
        elif schedule_type == "interval":
            try:
                seconds = int(v)
            except ValueError as exc:
                raise ValueError(
                    "interval schedule_value must be an integer seconds string"
                ) from exc
            if seconds < 1:
                raise ValueError("interval seconds must be >= 1")
        # on_demand allows any value; the worker ignores it.
        return v

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        for tag in v:
            if not tag or len(tag) > 50:
                raise ValueError(
                    "each tag must be 1-50 characters and non-empty"
                )
        return v


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    schedule_type: ScheduleType | None = None
    schedule_value: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=50)
    grace_period_seconds: int | None = Field(default=None, ge=0, le=86_400)
    expected_runtime_seconds: int | None = Field(default=None, ge=1)
    paused: bool | None = None
    tags: list[str] | None = None
    notification_settings: dict[str, object] | None = None


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    ping_token: str
    schedule_type: str
    schedule_value: str
    timezone: str
    grace_period_seconds: int
    expected_runtime_seconds: int | None
    status: str
    paused: bool
    tags: list[str]
    notification_settings: dict[str, object]
    created_at: datetime
    updated_at: datetime
