"""Brevo transactional email client.

Single-attempt send. Brevo's own SMTP plumbing handles greylisting and
remote-server retries; if we get an error here it's almost certainly a
config issue (unverified sender, bad API key) that retries won't fix.
"""
from __future__ import annotations

import httpx
import structlog

from apps.api.config import settings

log = structlog.get_logger("whycron.notify.email")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryFailed(RuntimeError):
    pass


async def send_brevo_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    to_name: str | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
    api_key: str | None = None,
    timeout_seconds: float = 10.0,
) -> str:
    """Send one transactional email via Brevo. Returns the messageId."""
    key = api_key or settings.brevo_api_key
    if not key:
        raise EmailDeliveryFailed(
            "BREVO_API_KEY is not configured — set it in .env"
        )

    recipient: dict[str, str] = {"email": to_email}
    if to_name:
        recipient["name"] = to_name

    payload = {
        "sender": {
            "name": sender_name or settings.brevo_sender_name,
            "email": sender_email or settings.brevo_sender_email,
        },
        "to": [recipient],
        "subject": subject,
        "textContent": text_body,
        "htmlContent": html_body,
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            BREVO_API_URL,
            json=payload,
            headers={
                "api-key": key,
                "accept": "application/json",
                "content-type": "application/json",
            },
        )

    if response.status_code >= 400:
        log.warning(
            "brevo_send_failed",
            status=response.status_code,
            body=response.text[:500],
            to=to_email,
        )
        raise EmailDeliveryFailed(
            f"Brevo returned {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    message_id = data.get("messageId", "")
    log.info("brevo_send_ok", message_id=message_id, to=to_email)
    return str(message_id)
