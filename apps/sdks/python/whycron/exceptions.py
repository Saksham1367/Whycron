"""Whycron SDK exception hierarchy."""
from __future__ import annotations


class WhycronError(Exception):
    """Base class for every error this SDK raises."""


class WhycronAPIError(WhycronError):
    """An HTTP request to the Whycron API returned a non-2xx response."""

    def __init__(self, status_code: int, message: str, body: object | None = None) -> None:
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class WhycronAuthError(WhycronAPIError):
    """401 — the API key is missing, malformed, expired, or revoked."""


class WhycronNotFoundError(WhycronAPIError):
    """404 — the resource does not exist or belongs to another organization."""


class WhycronRateLimitedError(WhycronAPIError):
    """429 — the caller is being rate limited."""
