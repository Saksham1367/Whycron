"""Dispatcher fan-out tests with mocked transports + optional live email.

The live email test sends ONE real message via Brevo to the address below.
It is gated on a configured ``BREVO_API_KEY``. Saksham's recipient is
hardcoded here; change before sharing the repo.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import (
    AIExplanation,
    AuditLog,
    Monitor,
    NotificationChannel,
    NotificationDelivery,
    Organization,
    Run,
)
from apps.api.services.notify.dispatcher import notify_for_run

LIVE_EMAIL_RECIPIENT = "sakshamdhingra1305@gmail.com"


# ── Fixture: failed run with explanation + channels ──────────────────────────


@pytest_asyncio.fixture
async def alertable_run(
    connected_db: None,
) -> AsyncIterator[dict[str, Any]]:
    """Create an org, monitor, failed run, and AIExplanation. Tests add
    their own channels (email/webhook/discord) per scenario."""
    test_id = uuid.uuid4().hex[:12]
    async with db.session() as s:
        org = Organization(
            name="Notify Test",
            slug=f"ntest-{test_id}",
            tier="free",
        )
        s.add(org)
        await s.flush()
        monitor = Monitor(
            organization_id=org.id,
            name=f"Backup Job {test_id}",
            ping_token=f"wcr_ntest_{test_id}",
            schedule_type="cron",
            schedule_value="0 2 * * *",
            timezone="UTC",
            grace_period_seconds=60,
        )
        s.add(monitor)
        await s.flush()
        run = Run(
            organization_id=org.id,
            monitor_id=monitor.id,
            state="failed",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            duration_ms=107_000,
            exit_code=1,
            log_excerpt="ERROR pg_dump: write to file failed: ENOSPC",
            failure_signature_hash="sha256:fake-signature",
        )
        s.add(run)
        await s.flush()
        explanation = AIExplanation(
            organization_id=org.id,
            run_id=run.id,
            prompt_version="v1",
            model=settings.anthropic_model_default,
            root_cause="Job failed because pg_dump ran out of disk space.",
            explanation=(
                "The backup volume hit 100% capacity before the archive "
                "could finish writing."
            ),
            suggested_fix="Rotate old backups or expand the volume.",
            confidence="high",
            input_tokens=512,
            output_tokens=180,
            cost_usd_micro=1432,
        )
        s.add(explanation)
        await s.commit()
        ctx = {
            "org_id": org.id,
            "monitor_id": monitor.id,
            "run_id": run.id,
            "explanation_id": explanation.id,
        }

    yield ctx

    async with db.session() as s:
        await s.execute(
            delete(NotificationDelivery).where(
                NotificationDelivery.organization_id == ctx["org_id"]
            )
        )
        await s.execute(
            delete(NotificationChannel).where(
                NotificationChannel.organization_id == ctx["org_id"]
            )
        )
        await s.execute(
            delete(AIExplanation).where(
                AIExplanation.organization_id == ctx["org_id"]
            )
        )
        await s.execute(
            delete(AuditLog).where(AuditLog.organization_id == ctx["org_id"])
        )
        await s.execute(
            delete(Run).where(Run.organization_id == ctx["org_id"])
        )
        await s.execute(
            delete(Monitor).where(Monitor.id == ctx["monitor_id"])
        )
        await s.execute(
            delete(Organization).where(Organization.id == ctx["org_id"])
        )
        await s.commit()


async def _add_channel(
    org_id: uuid.UUID,
    channel_type: str,
    config: dict[str, Any],
    name: str = "test channel",
) -> uuid.UUID:
    async with db.session() as s:
        channel = NotificationChannel(
            organization_id=org_id,
            type=channel_type,
            name=name,
            config=config,
            enabled=True,
        )
        s.add(channel)
        await s.commit()
        return channel.id


# ── Mocked transport tests ───────────────────────────────────────────────────


async def test_dispatcher_skips_when_no_channels_configured(
    alertable_run: dict[str, Any],
) -> None:
    counts = await notify_for_run(alertable_run["run_id"])
    assert counts == {"sent": 0, "failed": 0, "skipped": 0}

    async with db.session() as s:
        deliveries = (
            await s.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.organization_id
                    == alertable_run["org_id"]
                )
            )
        ).scalars().all()
    assert deliveries == []


async def test_dispatcher_skips_non_alertable_state(
    connected_db: None,
) -> None:
    test_id = uuid.uuid4().hex[:12]
    async with db.session() as s:
        org = Organization(
            name="Notify Skip",
            slug=f"nskip-{test_id}",
            tier="free",
        )
        s.add(org)
        await s.flush()
        monitor = Monitor(
            organization_id=org.id,
            name=f"Skip {test_id}",
            ping_token=f"wcr_nskip_{test_id}",
            schedule_type="cron",
            schedule_value="0 2 * * *",
        )
        s.add(monitor)
        await s.flush()
        run = Run(
            organization_id=org.id,
            monitor_id=monitor.id,
            state="succeeded",
            ended_at=datetime.now(timezone.utc),
        )
        s.add(run)
        await s.commit()
        run_id = run.id
        org_id = org.id
        m_id = monitor.id

    counts = await notify_for_run(run_id)
    assert counts["skipped"] == 1
    assert counts["sent"] == 0

    async with db.session() as s:
        await s.execute(delete(Run).where(Run.organization_id == org_id))
        await s.execute(delete(Monitor).where(Monitor.id == m_id))
        await s.execute(delete(Organization).where(Organization.id == org_id))
        await s.commit()


async def test_dispatcher_calls_email_transport(
    alertable_run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_send(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "fake-message-id"

    monkeypatch.setattr(
        "apps.api.services.notify.dispatcher.send_brevo_email", fake_send
    )

    await _add_channel(
        alertable_run["org_id"],
        "email",
        {"to": "ops@example.com"},
        name="Ops Inbox",
    )

    counts = await notify_for_run(alertable_run["run_id"])
    assert counts == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(calls) == 1
    assert calls[0]["to_email"] == "ops@example.com"
    assert "pg_dump" in calls[0]["subject"]
    assert "Root cause." in calls[0]["text_body"]

    async with db.session() as s:
        delivery = (
            await s.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.organization_id
                    == alertable_run["org_id"]
                )
            )
        ).scalar_one()
    assert delivery.status == "sent"
    assert delivery.channel_type == "email"


async def test_dispatcher_calls_webhook_transport(
    alertable_run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_send(url: str, payload: dict, **kwargs: Any) -> int:
        calls.append({"url": url, "payload": payload, **kwargs})
        return 200

    monkeypatch.setattr(
        "apps.api.services.notify.dispatcher.send_signed_webhook", fake_send
    )

    await _add_channel(
        alertable_run["org_id"],
        "webhook",
        {"url": "https://hooks.example.com/whycron", "secret": "topsecret"},
    )

    counts = await notify_for_run(alertable_run["run_id"])
    assert counts == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(calls) == 1
    payload = calls[0]["payload"]
    assert payload["event"] == "run.alerted"
    assert payload["monitor"]["name"].startswith("Backup Job")
    assert payload["run"]["state"] == "failed"
    assert payload["explanation"]["confidence"] == "high"
    assert calls[0]["secret"] == "topsecret"


async def test_dispatcher_calls_discord_transport(
    alertable_run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_send(webhook_url: str, **kwargs: Any) -> None:
        calls.append({"url": webhook_url, **kwargs})

    monkeypatch.setattr(
        "apps.api.services.notify.dispatcher.send_discord_message", fake_send
    )

    await _add_channel(
        alertable_run["org_id"],
        "discord",
        {"url": "https://discord.com/api/webhooks/1234/abcd"},
    )

    counts = await notify_for_run(alertable_run["run_id"])
    assert counts["sent"] == 1
    assert len(calls) == 1
    assert calls[0]["url"].startswith("https://discord.com/")


async def test_dispatcher_records_failure_without_stopping_other_channels(
    alertable_run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_email(**kwargs: Any) -> str:
        raise RuntimeError("Brevo refused: unverified sender")

    discord_calls: list[Any] = []

    async def succeeding_discord(webhook_url: str, **kwargs: Any) -> None:
        discord_calls.append(webhook_url)

    monkeypatch.setattr(
        "apps.api.services.notify.dispatcher.send_brevo_email", failing_email
    )
    monkeypatch.setattr(
        "apps.api.services.notify.dispatcher.send_discord_message",
        succeeding_discord,
    )

    await _add_channel(
        alertable_run["org_id"], "email", {"to": "ops@example.com"}
    )
    await _add_channel(
        alertable_run["org_id"],
        "discord",
        {"url": "https://discord.com/api/webhooks/1/2"},
    )

    counts = await notify_for_run(alertable_run["run_id"])
    assert counts == {"sent": 1, "failed": 1, "skipped": 0}
    assert len(discord_calls) == 1  # Discord still ran despite email failure

    async with db.session() as s:
        deliveries = (
            await s.execute(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.organization_id
                    == alertable_run["org_id"]
                )
                .order_by(NotificationDelivery.channel_type)
            )
        ).scalars().all()
    by_type = {d.channel_type: d for d in deliveries}
    assert by_type["email"].status == "failed"
    assert "unverified" in (by_type["email"].error_message or "")
    assert by_type["discord"].status == "sent"


async def test_dispatcher_skips_disabled_channel(
    alertable_run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enabled=False`` channels are not contacted."""
    calls: list[Any] = []

    async def fake_send(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "x"

    monkeypatch.setattr(
        "apps.api.services.notify.dispatcher.send_brevo_email", fake_send
    )

    async with db.session() as s:
        s.add(
            NotificationChannel(
                organization_id=alertable_run["org_id"],
                type="email",
                name="Disabled",
                config={"to": "ops@example.com"},
                enabled=False,
            )
        )
        await s.commit()

    counts = await notify_for_run(alertable_run["run_id"])
    assert counts["sent"] == 0
    assert calls == []


# ── Optional live test (gated on real Brevo key) ─────────────────────────────


@pytest.mark.skipif(
    not settings.brevo_api_key,
    reason="BREVO_API_KEY not configured — skipping live email send",
)
async def test_dispatcher_sends_real_email_via_brevo(
    alertable_run: dict[str, Any],
) -> None:
    """One real email goes out via Brevo. Check the configured recipient's
    inbox. Skipped when the API key is missing."""
    await _add_channel(
        alertable_run["org_id"],
        "email",
        {"to": LIVE_EMAIL_RECIPIENT},
        name="Live Test Inbox",
    )

    counts = await notify_for_run(alertable_run["run_id"])
    assert counts["sent"] == 1, (
        "Live Brevo send failed — verify BREVO_SENDER_EMAIL is a verified "
        "sender in your Brevo account. Check the notification_deliveries "
        "table for the error message."
    )

    async with db.session() as s:
        delivery = (
            await s.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.organization_id
                    == alertable_run["org_id"]
                )
            )
        ).scalar_one()
    assert delivery.status == "sent"
