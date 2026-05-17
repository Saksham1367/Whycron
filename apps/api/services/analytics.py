"""Server-side analytics — PostHog wrapper.

Used only for **conversion-funnel events** the backend is uniquely
positioned to know about (monitor created via API key, subscription
state changes from Polar, etc.). The frontend handles page views and
UI-level events directly via posthog-js.

This wrapper is intentionally fire-and-forget: a network failure to
PostHog must never break a user-facing request. We log a warning and
move on.

**Threading model.** The PostHog SDK can perform synchronous HTTP work
(notably its first ``/decide`` feature-flag probe at startup) that would
stall the asyncio event loop if invoked directly from a request handler.
We always run ``capture`` on a background thread via ``asyncio.to_thread``
so the route handler never blocks.

Privacy: we do NOT send log excerpts, monitor names, or any user-typed
content to PostHog. Only stable identifiers (uuid, tier) and counts.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

from apps.api.config import settings

log = structlog.get_logger("whycron.analytics")

_client = None
_client_initialized = False


def _get_client():
    """Lazy singleton. Returns ``None`` if PostHog isn't configured."""
    global _client, _client_initialized
    if _client_initialized:
        return _client
    _client_initialized = True
    if not settings.posthog_api_key:
        return None
    try:
        from posthog import Posthog

        _client = Posthog(
            project_api_key=settings.posthog_api_key,
            host=settings.posthog_host,
            # Disable feature-flag polling — we don't use flags from the
            # backend, and the probe call would block at startup.
            disable_geoip=True,
            feature_flags_request_timeout_seconds=1.0,
            sync_mode=False,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("posthog_client_init_failed", error=str(exc))
        _client = None
    return _client


def _capture_sync(
    distinct_id: str, event: str, properties: dict[str, Any]
) -> None:
    """Synchronous capture body. Called inside a worker thread."""
    client = _get_client()
    if client is None:
        return
    try:
        client.capture(
            distinct_id=distinct_id, event=event, properties=properties
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "posthog_capture_failed", event=event, error=str(exc)
        )


def capture(
    *,
    distinct_id: uuid.UUID | str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget event capture. Schedules a background task on the
    current event loop and returns immediately. Never raises.

    Safe to call from sync code too — if no loop is running, falls back
    to in-thread capture (cheap because the SDK queues internally).
    """
    distinct_id_str = str(distinct_id)
    props = properties or {}
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop — call directly. Used by sync callers in CLI scripts.
        _capture_sync(distinct_id_str, event, props)
        return
    # Schedule on a thread so we never block the request loop.
    loop.create_task(
        asyncio.to_thread(_capture_sync, distinct_id_str, event, props)
    )
