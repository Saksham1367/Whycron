"""Notification dispatcher — fans out one run's alert to every channel.

Called from the worker (``apps.worker.tasks.notify``) after either:

- the AI explainer finishes for a failed run, or
- the schedule scanner inserts a ``missed`` / ``timed_out`` row.

Per-channel attempts are independent. Each writes a
``notification_deliveries`` row with ``status='sent'`` or
``status='failed'``. A channel-level failure does not halt the fan-out;
RQ's job-level retry will not re-attempt this dispatcher (channel-level
re-delivery is V2 work).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from apps.api.config import settings
from apps.api.db import _async_url
from apps.api.models import (
    AIExplanation,
    Monitor,
    NotificationChannel,
    NotificationDelivery,
    Run,
    SlackInstallation,
)
from apps.api.services.crypto import decrypt
from apps.api.services.notify.discord import (
    DiscordDeliveryFailed,
    send_discord_message,
)
from apps.api.services.notify.email import EmailDeliveryFailed, send_brevo_email
from apps.api.services.notify.format import RenderedAlert, render_alert
from apps.api.services.notify.slack import (
    SlackDeliveryFailed,
    render_slack_blocks,
    send_slack_message,
)
from apps.api.services.notify.webhook import (
    WebhookDeliveryFailed,
    send_signed_webhook,
)

log = structlog.get_logger("whycron.notify.dispatcher")

# States that produce alerts. Succeeded/started never alert.
_ALERTABLE_STATES = ("failed", "missed", "timed_out", "late")


async def notify_for_run(
    run_id: uuid.UUID,
    *,
    session: AsyncSession | None = None,
) -> dict[str, int]:
    """Fan out alerts for one run. Returns counts ``{sent, failed, skipped}``.

    Idempotency is not enforced here — calling twice produces two sets of
    notification_deliveries. The caller (the RQ task) is expected to dispatch
    once per (run, scan event).
    """
    if session is not None:
        return await _dispatch_inner(session, run_id)
    engine = create_async_engine(_async_url(settings.database_url))
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            return await _dispatch_inner(s, run_id)
    finally:
        await engine.dispose()


async def _dispatch_inner(
    session: AsyncSession, run_id: uuid.UUID
) -> dict[str, int]:
    counts = {"sent": 0, "failed": 0, "skipped": 0}

    run = (
        await session.execute(select(Run).where(Run.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        log.warning("run_not_found", run_id=str(run_id))
        return counts
    if run.state not in _ALERTABLE_STATES:
        log.info(
            "skipping_non_alertable_state",
            run_id=str(run_id),
            state=run.state,
        )
        counts["skipped"] = 1
        return counts

    monitor = (
        await session.execute(
            select(Monitor).where(Monitor.id == run.monitor_id)
        )
    ).scalar_one()

    explanation = (
        await session.execute(
            select(AIExplanation)
            .where(AIExplanation.run_id == run_id)
            .order_by(AIExplanation.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    channels = (
        await session.execute(
            select(NotificationChannel).where(
                NotificationChannel.organization_id == run.organization_id,
                NotificationChannel.enabled.is_(True),
                NotificationChannel.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    if not channels:
        log.info(
            "no_channels_configured",
            org_id=str(run.organization_id),
            run_id=str(run_id),
        )
        return counts

    rendered = render_alert(monitor=monitor, run=run, explanation=explanation)

    for channel in channels:
        external_id: str | None = None
        try:
            external_id = await _send_to_channel(
                session, channel, rendered, run, monitor, explanation
            )
        except Exception as exc:  # noqa: BLE001 — we want to log + record any failure
            log.warning(
                "channel_delivery_failed",
                channel_id=str(channel.id),
                channel_type=channel.type,
                error=str(exc),
            )
            session.add(
                NotificationDelivery(
                    organization_id=run.organization_id,
                    run_id=run.id,
                    channel_id=channel.id,
                    channel_type=channel.type,
                    status="failed",
                    attempts=1,
                    last_attempt_at=datetime.now(timezone.utc),
                    error_message=str(exc)[:500],
                    payload_summary=_summary(channel, rendered),
                )
            )
            counts["failed"] += 1
            continue

        session.add(
            NotificationDelivery(
                organization_id=run.organization_id,
                run_id=run.id,
                channel_id=channel.id,
                channel_type=channel.type,
                status="sent",
                attempts=1,
                last_attempt_at=datetime.now(timezone.utc),
                payload_summary=_summary(channel, rendered),
                external_id=external_id,
            )
        )
        counts["sent"] += 1

    await session.commit()
    return counts


async def _send_to_channel(
    session: AsyncSession,
    channel: NotificationChannel,
    rendered: RenderedAlert,
    run: Run,
    monitor: Monitor,
    explanation: AIExplanation | None,
) -> str | None:
    """Returns a channel-side external_id (e.g. Slack ``ts``) or ``None``."""
    config = dict(channel.config or {})
    if channel.type == "email":
        to = config.get("to")
        if not to:
            raise ValueError("email channel missing 'to' in config")
        await send_brevo_email(
            to_email=to,
            to_name=config.get("name"),
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
        )
        return None

    if channel.type == "webhook":
        url = config.get("url")
        if not url:
            raise ValueError("webhook channel missing 'url' in config")
        await send_signed_webhook(
            url=url,
            payload=_webhook_payload(run, monitor, explanation),
            secret=config.get("secret"),
        )
        return None

    if channel.type == "discord":
        url = config.get("url")
        if not url:
            raise ValueError("discord channel missing 'url' in config")
        await send_discord_message(
            webhook_url=url,
            content=f"**{rendered.subject}**\n\n```{rendered.text_body[:1800]}```",
        )
        return None

    if channel.type == "slack":
        return await _send_slack(session, channel, rendered, run, monitor, explanation)

    raise ValueError(f"unsupported channel type: {channel.type!r}")


# ── Slack-specific helpers ──────────────────────────────────────────────────


async def _send_slack(
    session: AsyncSession,
    channel: NotificationChannel,
    rendered: RenderedAlert,
    run: Run,
    monitor: Monitor,
    explanation: AIExplanation | None,
) -> str:
    config = dict(channel.config or {})
    channel_id = config.get("channel_id")
    if not channel_id:
        raise ValueError("slack channel missing 'channel_id' in config")

    install = (
        await session.execute(
            select(SlackInstallation).where(
                SlackInstallation.organization_id == run.organization_id,
                SlackInstallation.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if install is None:
        raise ValueError(
            "Slack workspace is not connected for this organization. "
            "Reconnect at /channels."
        )

    bot_token = decrypt(install.bot_token_encrypted)
    thread_ts = await _find_thread_ts_for_incident(session, monitor.id, channel.id)

    blocks = render_slack_blocks(
        subject=rendered.subject,
        monitor_name=monitor.name,
        state=run.state,
        schedule=monitor.schedule_value,
        monitor_url=_monitor_url(monitor.id),
        explanation_root_cause=explanation.root_cause if explanation else None,
        explanation_text=explanation.explanation if explanation else None,
        explanation_fix=explanation.suggested_fix if explanation else None,
    )

    return await send_slack_message(
        bot_token=bot_token,
        channel_id=str(channel_id),
        text=rendered.subject,
        blocks=blocks,
        thread_ts=thread_ts,
    )


async def _find_thread_ts_for_incident(
    session: AsyncSession,
    monitor_id: uuid.UUID,
    channel_id: uuid.UUID,
) -> str | None:
    """Look up an existing thread to reply into for follow-up alerts on
    the same monitor + channel.

    Strategy: the most recent successfully-sent Slack delivery for this
    (monitor, channel) pair becomes the root of the thread. If we ever
    want to "close" a thread (e.g. after a recovery), we'd record that
    explicitly; for V2 we just keep replying to the latest sent ts.
    """
    row = (
        await session.execute(
            select(NotificationDelivery)
            .join(Run, Run.id == NotificationDelivery.run_id)
            .where(
                NotificationDelivery.channel_id == channel_id,
                NotificationDelivery.channel_type == "slack",
                NotificationDelivery.status == "sent",
                NotificationDelivery.external_id.is_not(None),
                Run.monitor_id == monitor_id,
            )
            .order_by(NotificationDelivery.last_attempt_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row.external_id if row is not None else None


def _monitor_url(monitor_id: uuid.UUID) -> str | None:
    if not settings.frontend_url:
        return None
    return f"{settings.frontend_url.rstrip('/')}/monitors/{monitor_id}"


def _webhook_payload(
    run: Run, monitor: Monitor, explanation: AIExplanation | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": "run.alerted",
        "monitor": {
            "id": str(monitor.id),
            "name": monitor.name,
            "schedule": monitor.schedule_value,
            "timezone": monitor.timezone,
        },
        "run": {
            "id": str(run.id),
            "state": run.state,
            "started_at": run.started_at.isoformat()
            if run.started_at
            else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "duration_ms": run.duration_ms,
            "exit_code": run.exit_code,
            "log_excerpt": run.log_excerpt,
            "failure_signature_hash": run.failure_signature_hash,
        },
        "explanation": None,
    }
    if explanation is not None:
        payload["explanation"] = {
            "id": str(explanation.id),
            "root_cause": explanation.root_cause,
            "explanation": explanation.explanation,
            "suggested_fix": explanation.suggested_fix,
            "confidence": explanation.confidence,
            "model": explanation.model,
            "prompt_version": explanation.prompt_version,
        }
    return payload


def _summary(
    channel: NotificationChannel, rendered: RenderedAlert
) -> str:
    return f"{channel.type}:{channel.name} — {rendered.subject[:120]}"
