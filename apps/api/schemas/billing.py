"""Billing request + response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CheckoutCreate(BaseModel):
    tier: Literal["pro", "team"] = Field(default="pro")


class CheckoutOut(BaseModel):
    checkout_url: str


class PortalOut(BaseModel):
    portal_url: str
