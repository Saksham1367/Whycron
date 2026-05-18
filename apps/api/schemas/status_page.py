"""Schemas for the status-page admin endpoints (Phase 14)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Slug rules: 3-40 chars, lowercase letters, digits, dashes. No leading or
# trailing dashes, no consecutive dashes. Must START with a letter so it
# can also live as a subdomain later (``acme.status.whycron.com``).
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")


class StatusPageConfig(BaseModel):
    """Current public-page state. Returned by ``GET /api/v1/status-page``."""

    slug: str | None
    headline: str | None
    public_monitor_count: int
    total_monitor_count: int
    public_url: str | None  # Server-resolved full URL when slug is set.


class StatusPageUpdate(BaseModel):
    """Body for ``PATCH /api/v1/status-page``.

    Pass ``slug=None`` to disable the public page entirely. Pass a string
    to set/change it. Omit the field to leave it untouched.
    """

    # ``None`` means "explicitly unset" — distinguished from "omitted"
    # using ``model_dump(exclude_unset=True)`` in the handler.
    slug: str | None = Field(default=None, max_length=40)
    headline: str | None = Field(default=None, max_length=200)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be 3-40 chars, lowercase letters / digits / "
                "dashes, start with a letter, end alphanumerically, no "
                "consecutive dashes."
            )
        return v
