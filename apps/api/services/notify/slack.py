"""Slack chat.postMessage transport.

Uses the org's installed bot token (encrypted in ``slack_installations``,
decrypted at send time). Returns the message ``ts`` so the dispatcher
can persist it on the ``notification_deliveries`` row and reply in
thread for subsequent alerts about the same incident.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

log = structlog.get_logger("whycron.notify.slack")

_SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


class SlackDeliveryFailed(RuntimeError):
    pass


async def send_slack_message(
    *,
    bot_token: str,
    channel_id: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    thread_ts: str | None = None,
    timeout_seconds: float = 10.0,
) -> str:
    """Post a message to Slack. Returns the message ``ts``.

    :param bot_token: ``xoxb-...`` value, decrypted from storage.
    :param channel_id: Slack channel id (e.g. ``C0123ABCD``). Use the
        id, not the name — names can change, ids are stable.
    :param text: Plain-text fallback. Required even when ``blocks`` is
        given (Slack uses it in notification previews + screen readers).
    :param blocks: Optional Block Kit payload for richer formatting.
    :param thread_ts: If provided, the message becomes a reply in this
        thread instead of a top-level post.
    """
    if not bot_token:
        raise SlackDeliveryFailed("missing bot_token (workspace not connected?)")
    if not channel_id:
        raise SlackDeliveryFailed("missing channel_id")

    payload: dict[str, Any] = {
        "channel": channel_id,
        "text": text[:3500],  # Slack's text field cap is generous; keep alerts terse
    }
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            _SLACK_POST_MESSAGE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    if response.status_code >= 400:
        log.warning(
            "slack_send_http_failed",
            status=response.status_code,
            body=response.text[:300],
        )
        raise SlackDeliveryFailed(
            f"Slack returned HTTP {response.status_code}: {response.text[:200]}"
        )

    body = response.json()
    if not body.get("ok"):
        err = body.get("error", "unknown")
        # Slack puts the per-block reason in response_metadata.messages —
        # e.g. ``[ERROR] invalid_block: must define text or fields``. Without
        # this, ``invalid_blocks`` alone is useless to diagnose.
        details = (body.get("response_metadata") or {}).get("messages") or []
        # Dump the failing payload so a teammate can replay it locally.
        # Safe to log: we don't put credentials in the payload.
        payload_dump = json.dumps(payload, ensure_ascii=False)[:4000]
        log.warning(
            "slack_send_failed",
            error=err,
            details=details,
            channel=channel_id,
            payload=payload_dump,
        )
        detail_str = f" ({'; '.join(details)})" if details else ""
        raise SlackDeliveryFailed(
            f"Slack chat.postMessage error: {err}{detail_str}"
        )

    ts = body.get("ts")
    if not ts:
        raise SlackDeliveryFailed("Slack response missing 'ts' field")
    return str(ts)


def render_slack_blocks(
    *,
    subject: str,
    monitor_name: str,
    state: str,
    schedule: str,
    monitor_url: str | None,
    explanation_root_cause: str | None = None,
    explanation_text: str | None = None,
    explanation_fix: str | None = None,
) -> list[dict[str, Any]]:
    """Build a Block Kit payload for an alert.

    Keeps the layout consistent: header with the subject, two-column
    fields for monitor/state/schedule, then the AI explanation as a
    section block if present.
    """
    state_emoji = {
        "failed": ":x:",
        "missed": ":hourglass_flowing_sand:",
        "timed_out": ":alarm_clock:",
        "late": ":hourglass:",
    }.get(state, ":warning:")

    # Slack hard caps every text field in a Block Kit payload. Exceeding
    # any of them produces ``invalid_blocks`` with no indication of which
    # block. Truncate defensively.
    HEADER_MAX = 150
    FIELD_TEXT_MAX = 2000
    SECTION_TEXT_MAX = 2900  # 3000 cap; leave headroom for joiners

    header_text = f"{state_emoji} {subject}"
    if len(header_text) > HEADER_MAX:
        header_text = header_text[: HEADER_MAX - 1] + "…"

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text, "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Monitor*\n{monitor_name}"[:FIELD_TEXT_MAX]},
                {"type": "mrkdwn", "text": f"*Status*\n`{state}`"[:FIELD_TEXT_MAX]},
                {"type": "mrkdwn", "text": f"*Schedule*\n`{schedule}`"[:FIELD_TEXT_MAX]},
            ],
        },
    ]

    if explanation_root_cause or explanation_text:
        lines: list[str] = []
        if explanation_root_cause:
            lines.append(f"*Root cause:* {explanation_root_cause}")
        if explanation_text:
            lines.append(explanation_text)
        if explanation_fix:
            lines.append(f"*Suggested fix:* {explanation_fix}")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n\n".join(lines)[:SECTION_TEXT_MAX],
                },
            }
        )

    # Slack rejects button blocks whose ``url`` points at localhost /
    # private IPs (its frontend treats them as "invalid_blocks"). Only
    # attach the button when the URL is publicly reachable — in dev that
    # means we silently drop it, which is fine.
    if monitor_url and _is_public_url(monitor_url):
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open in Whycron",
                        },
                        "url": monitor_url,
                    }
                ],
            }
        )

    return blocks


def _is_public_url(url: str) -> bool:
    lower = url.lower()
    return not any(
        marker in lower
        for marker in (
            "//localhost",
            "//127.",
            "//0.0.0.0",
            "//192.168.",
            "//10.",
            "//[::1]",
        )
    )
