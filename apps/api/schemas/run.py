"""Run + AI explanation response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AIExplanationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt_version: str
    model: str
    root_cause: str
    explanation: str
    suggested_fix: str | None
    confidence: str
    input_tokens: int
    output_tokens: int
    cost_usd_micro: int
    user_feedback: str | None
    cached_from_signature_hash: str | None
    created_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitor_id: uuid.UUID
    state: str
    run_external_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    exit_code: int | None
    log_excerpt: str | None
    log_size_bytes: int | None
    failure_signature_hash: str | None
    created_at: datetime


class RunDetail(RunOut):
    """Single-run response — adds the latest AI explanation if any."""

    explanation: AIExplanationOut | None = None


class FeedbackBody(BaseModel):
    feedback: Literal["helpful", "not_helpful"] = Field(...)
