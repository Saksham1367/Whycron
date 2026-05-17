"""HMAC-signed outbound webhook transport.

Every payload is signed so customers can verify it came from us
(CONTEXT.md §7.3 — "HMAC-sign every outgoing webhook payload"). The signing
secret is per-org when the user supplies one in the channel config; we fall
back to ``settings.webhook_signing_secret`` so unconfigured channels still
sign with a global secret rather than send unsigned.

Retry policy: 5 attempts total with exponential backoff (10s → 30s → 60s →
120s), 10s timeout per attempt, no redirect-following. Total worst case
~4 minutes wall-clock per recipient. Tests inject ``delays_seconds=[]``
to make retries instantaneous.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog

from apps.api.config import settings
from apps.api.services.notify.ssrf import validate_webhook_url

log = structlog.get_logger("whycron.notify.webhook")


DEFAULT_RETRY_DELAYS = (10, 30, 60, 120)
DEFAULT_TIMEOUT_SECONDS = 10.0


class WebhookDeliveryFailed(RuntimeError):
    """Raised after all retry attempts have been exhausted."""


def sign_payload(
    secret: str, body: bytes, *, timestamp: int | None = None
) -> dict[str, str]:
    """Return the HMAC-SHA256 headers for ``body``.

    Receivers verify by:
        1. Reading ``X-Whycron-Timestamp`` and rejecting if it's > 5 min old.
        2. Computing ``HMAC-SHA256(secret, f"{ts}.".encode() + body)`` and
           comparing the hex digest to the ``v1=`` portion of
           ``X-Whycron-Signature`` with ``hmac.compare_digest``.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    message = f"{ts}.".encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return {
        "X-Whycron-Timestamp": str(ts),
        "X-Whycron-Signature": f"v1={digest}",
    }


async def send_signed_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    secret: str | None = None,
    delays_seconds: tuple[int, ...] | list[int] = DEFAULT_RETRY_DELAYS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """POST ``payload`` to ``url`` with HMAC signature and retry.

    Returns the final HTTP status code on success. Raises ``UnsafeWebhookURL``
    if the SSRF guard rejects the URL, or ``WebhookDeliveryFailed`` if every
    attempt errored.
    """
    # Fail fast on the cheap check before doing DNS.
    sig_secret = secret or settings.webhook_signing_secret
    if not sig_secret:
        raise WebhookDeliveryFailed(
            "no signing secret configured (WEBHOOK_SIGNING_SECRET unset and "
            "no per-channel secret supplied)"
        )

    validate_webhook_url(url)

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    base_headers = {
        "Content-Type": "application/json",
        "User-Agent": "Whycron/1.0",
        **sign_payload(sig_secret, body),
    }

    max_attempts = len(delays_seconds) + 1
    last_error: str | None = None
    for attempt in range(max_attempts):
        if attempt > 0:
            await asyncio.sleep(delays_seconds[attempt - 1])
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    url,
                    content=body,
                    headers=base_headers,
                    follow_redirects=False,  # critical — guards re-validation
                )
        except httpx.RequestError as exc:
            last_error = f"network: {exc!r}"
            log.warning(
                "webhook_attempt_failed",
                url=url,
                attempt=attempt + 1,
                error=last_error,
            )
            continue

        if 200 <= response.status_code < 300:
            return response.status_code
        if 300 <= response.status_code < 400:
            last_error = f"unexpected redirect {response.status_code}"
            break  # do not retry redirects
        if 400 <= response.status_code < 500:
            last_error = f"client error {response.status_code}"
            break  # do not retry client errors
        # 5xx → retry
        last_error = f"server error {response.status_code}"
        log.warning(
            "webhook_attempt_failed",
            url=url,
            attempt=attempt + 1,
            status=response.status_code,
        )

    raise WebhookDeliveryFailed(last_error or "all attempts failed")
