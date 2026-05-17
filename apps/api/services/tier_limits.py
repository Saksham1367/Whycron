"""Tier limit lookups + helpers shared by the dashboard API.

These limits live alongside CONTEXT.md §2 and DECISIONS.md #4. ``-1``
means "unlimited" and is returned by ``monitors_limit_for_tier`` so the
account API can communicate it to the frontend without a magic infinity
value.
"""
from __future__ import annotations

import secrets


_MONITOR_LIMITS: dict[str, int] = {
    "free": 5,
    "pro": 25,
    "team": 100,
    "business": 500,
    "enterprise": -1,
}

# Free tier: 100 AI explanations / month. Paid: unlimited (subject to the
# §8.3 budget alarm at $10/org/month — not yet implemented).
_AI_EXPLANATION_LIMITS: dict[str, int] = {
    "free": 100,
    "pro": -1,
    "team": -1,
    "business": -1,
    "enterprise": -1,
}


def monitors_limit_for_tier(tier: str) -> int:
    return _MONITOR_LIMITS.get(tier, _MONITOR_LIMITS["free"])


def ai_explanations_limit_for_tier(tier: str) -> int:
    return _AI_EXPLANATION_LIMITS.get(tier, _AI_EXPLANATION_LIMITS["free"])


def is_unlimited(limit: int) -> bool:
    return limit < 0


def generate_ping_token() -> str:
    """Return a new opaque ping token.

    Format: ``wcr_`` + 22 URL-safe base64 chars from 16 random bytes
    (~128 bits of entropy, comfortably beyond brute-forcing). The
    ``ping_token`` column carries a UNIQUE constraint that catches the
    astronomical-odds collision.
    """
    return f"wcr_{secrets.token_urlsafe(16)}"
