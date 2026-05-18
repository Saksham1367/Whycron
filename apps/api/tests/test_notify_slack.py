"""Slack dispatcher delivery + threaded follow-ups (Phase 13)."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

from apps.api.db import db
from apps.api.models import (
    AuditLog,
    Monitor,
    NotificationChannel,
    NotificationDelivery,
    Organization,
    Run,
    SlackInstallation,
)
from apps.api.services.crypto import encrypt
from apps.api.services.notify.dispatcher import notify_for_run


# ── Fakes for httpx ──────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeAsyncClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self._responses.pop(0)


# ── Crypto fixture ───────────────────────────────────────────────────────────


@pytest.fixture
def crypto_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr("apps.api.config.settings.encryption_key", key)
    from apps.api.services import crypto as crypto_mod

    crypto_mod._fernet.cache_clear()
    return key


# ── Per-test org + monitor + failed run + slack install + channel ───────────


@pytest_asyncio.fixture
async def alertable_slack_setup(
    connected_db: None, crypto_key: str
) -> AsyncIterator[dict[str, Any]]:
    test_id = uuid.uuid4().hex[:12]
    async with db.session() as s:
        org = Organization(
            name="Slack Test",
            slug=f"slack-{test_id}",
            tier="free",
        )
        s.add(org)
        await s.flush()
        monitor = Monitor(
            organization_id=org.id,
            name=f"Backup Job {test_id}",
            ping_token=f"wcr_slack_{test_id}",
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
            duration_ms=12_345,
            exit_code=1,
            log_excerpt="ERROR: disk full",
        )
        s.add(run)
        await s.flush()
        install = SlackInstallation(
            organization_id=org.id,
            team_id="T1",
            team_name="Workspace",
            bot_user_id="U_BOT",
            bot_token_encrypted=encrypt("xoxb-fake-token"),
            scopes="chat:write",
            app_id="A1",
            authed_user_id="U_USER",
        )
        s.add(install)
        await s.flush()
        channel = NotificationChannel(
            organization_id=org.id,
            type="slack",
            name="alerts-slack",
            config={"channel_id": "C123", "channel_name": "alerts"},
            enabled=True,
        )
        s.add(channel)
        await s.commit()

        ctx = {
            "org_id": org.id,
            "monitor_id": monitor.id,
            "run_id": run.id,
            "channel_id": channel.id,
        }

    yield ctx

    async with db.session() as s:
        for table in (
            NotificationDelivery,
            NotificationChannel,
            AuditLog,
            Run,
            SlackInstallation,
            Monitor,
        ):
            col = getattr(
                table, "organization_id", getattr(table, "id", None)
            )
            if table is Monitor:
                await s.execute(delete(Monitor).where(Monitor.id == ctx["monitor_id"]))
            else:
                await s.execute(
                    delete(table).where(table.organization_id == ctx["org_id"])
                )
        await s.execute(
            delete(Organization).where(Organization.id == ctx["org_id"])
        )
        await s.commit()


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_slack_delivery_stores_ts_as_external_id(
    alertable_slack_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(
        [_FakeResponse(200, {"ok": True, "ts": "1700000000.001"})]
    )
    monkeypatch.setattr(
        "apps.api.services.notify.slack.httpx.AsyncClient",
        lambda **_: fake,
    )

    counts = await notify_for_run(alertable_slack_setup["run_id"])
    assert counts == {"sent": 1, "failed": 0, "skipped": 0}, counts

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://slack.com/api/chat.postMessage"
    body = call["json"]
    assert body["channel"] == "C123"
    assert "thread_ts" not in body  # first delivery — no thread yet
    assert call["headers"]["Authorization"] == "Bearer xoxb-fake-token"

    async with db.session() as s:
        delivery = (
            await s.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.run_id
                    == alertable_slack_setup["run_id"]
                )
            )
        ).scalar_one()
    assert delivery.status == "sent"
    assert delivery.channel_type == "slack"
    assert delivery.external_id == "1700000000.001"


async def test_second_failure_replies_in_thread(
    alertable_slack_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # First failure — establishes the thread.
    first_fake = _FakeAsyncClient(
        [_FakeResponse(200, {"ok": True, "ts": "1700000000.111"})]
    )
    monkeypatch.setattr(
        "apps.api.services.notify.slack.httpx.AsyncClient",
        lambda **_: first_fake,
    )
    await notify_for_run(alertable_slack_setup["run_id"])

    # Create a second failed run on the same monitor.
    async with db.session() as s:
        run2 = Run(
            organization_id=alertable_slack_setup["org_id"],
            monitor_id=alertable_slack_setup["monitor_id"],
            state="failed",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            exit_code=1,
            log_excerpt="ERROR: disk full (again)",
        )
        s.add(run2)
        await s.commit()
        run2_id = run2.id

    # Second delivery should carry thread_ts = first ts.
    second_fake = _FakeAsyncClient(
        [_FakeResponse(200, {"ok": True, "ts": "1700000001.222"})]
    )
    monkeypatch.setattr(
        "apps.api.services.notify.slack.httpx.AsyncClient",
        lambda **_: second_fake,
    )
    await notify_for_run(run2_id)

    assert len(second_fake.calls) == 1
    body = second_fake.calls[0]["json"]
    assert body["thread_ts"] == "1700000000.111"


async def test_slack_send_failure_records_failed_delivery(
    alertable_slack_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(
        [_FakeResponse(200, {"ok": False, "error": "channel_not_found"})]
    )
    monkeypatch.setattr(
        "apps.api.services.notify.slack.httpx.AsyncClient",
        lambda **_: fake,
    )

    counts = await notify_for_run(alertable_slack_setup["run_id"])
    assert counts == {"sent": 0, "failed": 1, "skipped": 0}

    async with db.session() as s:
        delivery = (
            await s.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.run_id
                    == alertable_slack_setup["run_id"]
                )
            )
        ).scalar_one()
    assert delivery.status == "failed"
    assert "channel_not_found" in (delivery.error_message or "")


async def test_slack_channel_without_install_fails_cleanly(
    alertable_slack_setup: dict[str, Any],
) -> None:
    # Soft-delete the install so the dispatcher's lookup returns nothing.
    async with db.session() as s:
        install = (
            await s.execute(
                select(SlackInstallation).where(
                    SlackInstallation.organization_id
                    == alertable_slack_setup["org_id"]
                )
            )
        ).scalar_one()
        install.deleted_at = datetime.now(timezone.utc)
        await s.commit()

    counts = await notify_for_run(alertable_slack_setup["run_id"])
    assert counts == {"sent": 0, "failed": 1, "skipped": 0}

    async with db.session() as s:
        delivery = (
            await s.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.run_id
                    == alertable_slack_setup["run_id"]
                )
            )
        ).scalar_one()
    assert delivery.status == "failed"
    assert "not connected" in (delivery.error_message or "").lower()
