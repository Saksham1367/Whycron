"""Multi-pattern secret redaction.

This module is a V1 launch blocker (CLAUDE.md rule 6, CONTEXT.md §7.2).
Every user log payload MUST pass through ``redact()`` before it is

    1. written to our database, and
    2. sent to the Anthropic API.

Patterns are evaluated in a deliberate order: specific patterns first so the
correct ``type`` is attributed to each match, then the catch-all
high-entropy regex last to capture anything we don't recognize. Replacement
markers contain ``[`` ``]`` ``:`` characters that no pattern's character
class can match, so ``redact()`` is idempotent: running it twice on the
same input is a no-op.

This file is a living document. New patterns are added here as they are
discovered in production logs.
"""
from __future__ import annotations

import re
from re import Pattern

PLACEHOLDER = "[REDACTED:{type}]"

# Each entry: (label, compiled regex). Specific → general top-to-bottom.
_PATTERNS: list[tuple[str, Pattern[str]]] = [
    # AWS
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "aws_secret_key",
        re.compile(r"aws_secret_access_key\s*=\s*\S+", re.IGNORECASE),
    ),
    # GitHub — fine-grained PAT first (longest), then classic prefixes
    ("github_fine_grained_pat", re.compile(r"github_pat_[A-Za-z0-9_]{82}")),
    ("github_token", re.compile(r"gh[psour]_[A-Za-z0-9]{36,}")),
    # LLM providers — Anthropic before OpenAI; both start with "sk-" but
    # Anthropic's key contains hyphens that fall outside OpenAI's char class.
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]+")),
    # Slack
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]+")),
    # Stripe — the underscore separator distinguishes from OpenAI's hyphen.
    ("stripe_secret_key", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]+")),
    ("stripe_publishable_key", re.compile(r"pk_(?:live|test)_[A-Za-z0-9]+")),
    # OpenAI — runs after Anthropic + Stripe so it doesn't shadow them.
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    # HTTP auth
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    # Database connection strings with embedded credentials
    (
        "db_connection_string",
        re.compile(
            r"(?:postgres|postgresql|mysql|mongodb|redis)(?:\+\w+)?://[^@\s]+@[^/\s]+"
        ),
    ),
    # Private IP ranges (RFC1918) — common in logs that leak internal topology.
    (
        "private_ip",
        re.compile(
            r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3})\b"
        ),
    ),
    # PII — basic email regex (good enough for logs; not RFC-compliant).
    (
        "email",
        re.compile(
            r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}"
        ),
    ),
]

# Credit-card candidates require a Luhn check, so they're handled in code,
# not via a single regex sub.
_CC_CANDIDATE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

# Generic high-entropy catch-all for anything we don't specifically pattern.
# Runs last; markers like ``[REDACTED:foo]`` cannot trigger it because
# brackets and colons fall outside this character class. The longest current
# marker is 31 chars, comfortably under the 32-char minimum here — the
# ``test_marker_length_invariant`` test locks that down.
_HIGH_ENTROPY = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")


def _luhn_valid(digits: str) -> bool:
    """Standard Luhn checksum on a string of digits (no separators)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_credit_cards(text: str) -> str:
    def _maybe(match: re.Match[str]) -> str:
        raw = match.group()
        digits = re.sub(r"[ -]", "", raw)
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            return PLACEHOLDER.format(type="credit_card")
        return raw

    return _CC_CANDIDATE.sub(_maybe, text)


def redact(text: str) -> str:
    """Apply every pattern in order. Returns the redacted text.

    Idempotent: ``redact(redact(x)) == redact(x)`` for all inputs.
    """
    if not text:
        return text
    for label, pattern in _PATTERNS:
        text = pattern.sub(PLACEHOLDER.format(type=label), text)
    text = _redact_credit_cards(text)
    text = _HIGH_ENTROPY.sub(PLACEHOLDER.format(type="high_entropy"), text)
    return text


def all_pattern_labels() -> list[str]:
    """Introspection helper for tests + admin UI."""
    return [label for label, _ in _PATTERNS] + ["credit_card", "high_entropy"]
