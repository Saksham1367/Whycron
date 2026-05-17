"""Schema round-trip — proves every model writes and reads back.

This test runs against the live Postgres in docker-compose and exercises the
full schema in one go: an org, a user, a monitor, a run, an AI explanation,
a notification channel, a delivery, an audit log entry, and an API key.

The conftest fixture wraps the whole test in a transaction that is rolled
back at the end, so repeated runs do not accumulate data.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import (
    AIExplanation,
    APIKey,
    AuditLog,
    Monitor,
    NotificationChannel,
    NotificationDelivery,
    Organization,
    Run,
    User,
)


@pytest.mark.asyncio
async def test_full_schema_roundtrip(session: AsyncSession) -> None:
    org = Organization(name="Forgebit", slug="forgebit", tier="free")
    session.add(org)
    await session.flush()

    user = User(
        organization_id=org.id,
        supabase_user_id="sb-test-001",
        email="ha224763@ucf.edu",
        name="Saksham",
        role="owner",
    )
    session.add(user)
    await session.flush()

    monitor = Monitor(
        organization_id=org.id,
        name="Nightly PostgreSQL Backup",
        ping_token="wcr_ping_test_abc123",
        schedule_type="cron",
        schedule_value="0 2 * * *",
        timezone="UTC",
        grace_period_seconds=120,
        expected_runtime_seconds=900,
        status="healthy",
        tags=["db", "backup"],
    )
    session.add(monitor)
    await session.flush()

    run = Run(
        organization_id=org.id,
        monitor_id=monitor.id,
        run_external_id="run-001",
        state="failed",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=107_000,
        exit_code=1,
        log_excerpt="ERROR: disk full while writing pg_dump archive",
        log_size_bytes=4096,
        failure_signature_hash="sha256:abc123",
        metadata_json={"host": "worker-01", "version": "1.4.2"},
    )
    session.add(run)
    await session.flush()

    explanation = AIExplanation(
        organization_id=org.id,
        run_id=run.id,
        prompt_version="v1",
        model="claude-haiku-4-5-20251001",
        root_cause=(
            "Job failed because the backup volume filled up while pg_dump "
            "was writing the archive."
        ),
        explanation=(
            "The job connected and started dumping data correctly, but the "
            "destination mount reached 100% capacity before the archive "
            "could finish writing."
        ),
        suggested_fix=(
            "Rotate old backups or expand the backup volume before retrying."
        ),
        confidence="high",
        input_tokens=1240,
        output_tokens=180,
        cost_usd_micro=4200,
    )
    session.add(explanation)

    channel = NotificationChannel(
        organization_id=org.id,
        type="email",
        name="On-call inbox",
        config={"to": "alerts@example.com"},
        enabled=True,
    )
    session.add(channel)
    await session.flush()

    delivery = NotificationDelivery(
        organization_id=org.id,
        run_id=run.id,
        channel_id=channel.id,
        channel_type="email",
        status="sent",
        attempts=1,
        last_attempt_at=datetime.now(timezone.utc),
        payload_summary="email to alerts@example.com (subject: backup failed)",
    )
    session.add(delivery)

    audit = AuditLog(
        organization_id=org.id,
        user_id=user.id,
        action="monitor.create",
        entity_type="monitor",
        entity_id=monitor.id,
        diff={"after": {"name": monitor.name}},
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    session.add(audit)

    api_key = APIKey(
        organization_id=org.id,
        user_id=user.id,
        name="CI deploy key",
        key_hash="$2b$12$bcrypt_hash_placeholder_not_a_real_hash_just_text",
        key_prefix="wcr_live_a8f3",
        scopes=["monitors:read", "monitors:write"],
    )
    session.add(api_key)
    await session.flush()

    # ── Read every row back and verify it round-tripped intact ───────────
    fetched_org = (
        await session.execute(select(Organization).where(Organization.id == org.id))
    ).scalar_one()
    assert fetched_org.tier == "free"
    assert fetched_org.features == {}

    fetched_monitor = (
        await session.execute(select(Monitor).where(Monitor.id == monitor.id))
    ).scalar_one()
    assert fetched_monitor.tags == ["db", "backup"]
    assert fetched_monitor.notification_settings == {}
    assert fetched_monitor.paused is False

    fetched_run = (
        await session.execute(select(Run).where(Run.id == run.id))
    ).scalar_one()
    assert fetched_run.metadata_json == {"host": "worker-01", "version": "1.4.2"}
    assert fetched_run.exit_code == 1

    fetched_explanation = (
        await session.execute(
            select(AIExplanation).where(AIExplanation.run_id == run.id)
        )
    ).scalar_one()
    assert fetched_explanation.confidence == "high"
    assert fetched_explanation.cost_usd_micro == 4200

    fetched_delivery = (
        await session.execute(
            select(NotificationDelivery).where(NotificationDelivery.id == delivery.id)
        )
    ).scalar_one()
    assert fetched_delivery.attempts == 1

    fetched_audit = (
        await session.execute(select(AuditLog).where(AuditLog.id == audit.id))
    ).scalar_one()
    assert fetched_audit.action == "monitor.create"
    # asyncpg returns INET as ipaddress.* — coerce to str for assertion.
    assert str(fetched_audit.ip_address).startswith("127.0.0.1")

    fetched_key = (
        await session.execute(select(APIKey).where(APIKey.id == api_key.id))
    ).scalar_one()
    assert fetched_key.scopes == ["monitors:read", "monitors:write"]
    assert fetched_key.revoked_at is None


@pytest.mark.asyncio
async def test_run_external_id_dedup_index(session: AsyncSession) -> None:
    """The partial unique index on (monitor_id, run_external_id) must reject
    duplicate external IDs for the same monitor."""
    from sqlalchemy.exc import IntegrityError

    org = Organization(name="DedupOrg", slug="dedup-org-test")
    session.add(org)
    await session.flush()

    monitor = Monitor(
        organization_id=org.id,
        name="Dedup test",
        ping_token="wcr_ping_dedup_test",
        schedule_type="cron",
        schedule_value="*/5 * * * *",
    )
    session.add(monitor)
    await session.flush()

    session.add(
        Run(
            organization_id=org.id,
            monitor_id=monitor.id,
            run_external_id="dup-key",
            state="started",
        )
    )
    await session.flush()

    session.add(
        Run(
            organization_id=org.id,
            monitor_id=monitor.id,
            run_external_id="dup-key",
            state="started",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
