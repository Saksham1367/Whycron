"""Discord webhook transport.

Discord webhook URLs are public-facing (``discord.com/api/webhooks/...``)
so the SSRF guard's "must resolve to a public IP" requirement is satisfied
naturally. We still validate via the same guard for defense in depth — and
to catch typos where the URL points at the user's own infrastructure.
"""
from __future__ import annotations

import httpx
import structlog

from apps.api.services.notify.ssrf import validate_webhook_url

log = structlog.get_logger("whycron.notify.discord")


class DiscordDeliveryFailed(RuntimeError):
    pass


async def send_discord_message(
    webhook_url: str,
    *,
    content: str | None = None,
    embeds: list[dict] | None = None,
    timeout_seconds: float = 10.0,
) -> None:
    """POST a message to a Discord channel via its webhook URL."""
    validate_webhook_url(webhook_url)

    payload: dict[str, object] = {}
    if content:
        payload["content"] = content[:2000]  # Discord's hard limit
    if embeds:
        payload["embeds"] = embeds
    if not payload:
        raise DiscordDeliveryFailed("must provide content or embeds")

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            webhook_url, json=payload, follow_redirects=False
        )

    if response.status_code >= 400:
        log.warning(
            "discord_send_failed",
            status=response.status_code,
            body=response.text[:500],
        )
        raise DiscordDeliveryFailed(
            f"Discord returned {response.status_code}: {response.text[:200]}"
        )
