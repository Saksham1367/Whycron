"""One-shot Slack debug script — bisect which Block Kit block triggers
``invalid_blocks``.

Reads the latest non-deleted ``SlackInstallation`` for any org, decrypts
the bot token, and posts a sequence of progressively-richer messages to
the channel id provided on the command line. Each response is printed
verbatim. The first attempt to fail tells us which block is wrong.

Usage::

    uv run python scripts/slack_debug.py <SLACK_CHANNEL_ID>

Get the channel id by running this in another window:

    docker compose exec postgres psql -U whycron -d whycron -c \
        "SELECT config->>'channel_id' FROM notification_channels WHERE type='slack';"
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from apps.api.db import _async_url, db  # noqa: E402
from apps.api.models import SlackInstallation  # noqa: E402
from apps.api.services.crypto import decrypt  # noqa: E402
from apps.api.services.notify.slack import render_slack_blocks  # noqa: E402

URL = "https://slack.com/api/chat.postMessage"


async def _get_token() -> tuple[str, str]:
    await db.connect()
    try:
        async with db.session() as s:
            row = (
                await s.execute(
                    select(SlackInstallation)
                    .where(SlackInstallation.deleted_at.is_(None))
                    .order_by(SlackInstallation.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                raise RuntimeError(
                    "No SlackInstallation found in DB — connect a workspace first."
                )
            return decrypt(row.bot_token_encrypted), row.team_name
    finally:
        await db.disconnect()


async def _post(
    client: httpx.AsyncClient,
    token: str,
    channel: str,
    payload: dict,
    label: str,
) -> bool:
    print(f"\n=== {label} ===")
    print("REQUEST PAYLOAD:")
    print(json.dumps(payload, indent=2))
    resp = await client.post(
        URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    body = resp.json()
    print("RESPONSE:")
    print(json.dumps(body, indent=2))
    ok = bool(body.get("ok"))
    print(f"=> {'OK' if ok else 'FAIL'}")
    return ok


async def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    channel_id = sys.argv[1]

    token, team_name = await _get_token()
    print(f"Using bot token for workspace: {team_name}")
    print(f"Posting to channel id: {channel_id}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Test 1 — plain text only. If this fails, the issue is auth /
        # channel / bot not in channel, NOT blocks.
        if not await _post(
            client,
            token,
            channel_id,
            {"channel": channel_id, "text": "Whycron debug: plain text"},
            "Test 1 — plain text only",
        ):
            print(
                "\nPlain text failed — the issue is NOT blocks. Check bot scope, "
                "channel id, or /invite @whycron in the channel."
            )
            return 2

        # Test 2 — header block only.
        await _post(
            client,
            token,
            channel_id,
            {
                "channel": channel_id,
                "text": "Whycron debug: header only",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": ":x: Whycron debug header",
                            "emoji": True,
                        },
                    }
                ],
            },
            "Test 2 — header only",
        )

        # Test 3 — header + section with fields.
        await _post(
            client,
            token,
            channel_id,
            {
                "channel": channel_id,
                "text": "Whycron debug: header + section",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": ":x: Header + section",
                            "emoji": True,
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": "*Monitor*\nDebug job"},
                            {"type": "mrkdwn", "text": "*Status*\n`failed`"},
                            {"type": "mrkdwn", "text": "*Schedule*\n`*/5 * * * *`"},
                        ],
                    },
                ],
            },
            "Test 3 — header + section",
        )

        # Test 4 — the exact production renderer output (no URL, so no button).
        prod_blocks = render_slack_blocks(
            subject="[Whycron] Test Monitor: a sample root cause",
            monitor_name="Test Monitor",
            state="failed",
            schedule="*/5 * * * *",
            monitor_url=None,
            explanation_root_cause="Pipe broke open.",
            explanation_text="The downstream service rejected the payload.",
            explanation_fix="Retry with a smaller batch.",
        )
        await _post(
            client,
            token,
            channel_id,
            {
                "channel": channel_id,
                "text": "Whycron debug: full prod blocks",
                "blocks": prod_blocks,
            },
            "Test 4 — full production blocks",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
