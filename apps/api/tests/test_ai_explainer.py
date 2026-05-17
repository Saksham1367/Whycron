"""AI explainer service tests.

Most tests use a fake Anthropic client so the suite stays fast and key-free.
The final test in this file is gated on ``ANTHROPIC_API_KEY`` being present
in the environment; if set, it makes a single real round-trip to Claude.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
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
    Organization,
    Run,
)
from apps.api.services.ai_explainer import (
    _FREE_TIER_MONTHLY_QUOTA,
    PROMPT_VERSION,
    explain_failure,
)


# ── Fake Anthropic client ────────────────────────────────────────────────────


class _FakeContentBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeUsage:
    def __init__(
        self,
        input_tokens: int = 100,
        output_tokens: int = 60,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _FakeResponse:
    def __init__(self, text: str, usage: _FakeUsage) -> None:
        self.content = [_FakeContentBlock(text)]
        self.usage = usage


class _FakeMessages:
    def __init__(self, text: str, usage: _FakeUsage) -> None:
        self._text = text
        self._usage = usage
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self._text, self._usage)


class FakeAnthropic:
    """Drop-in stand-in for ``anthropic.AsyncAnthropic``."""

    def __init__(
        self,
        text: str = (
            "Job failed because `pg_dump` returned ENOSPC.\n\n"
            "The backup volume reached 100% capacity before the archive "
            "could finish writing.\n\n"
            "Rotate old backups or expand the backup volume before retrying."
        ),
        usage: _FakeUsage | None = None,
    ) -> None:
        self.messages = _FakeMessages(text, usage or _FakeUsage())


# ── Seed fixture for failed runs ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_failed_run(connected_db: None) -> Any:
    """Create an org + monitor + one failed run; clean up after."""
    test_id = uuid.uuid4().hex[:12]
    async with db.session() as s:
        org = Organization(
            name="Explainer Test",
            slug=f"etest-{test_id}",
            tier="free",
        )
        s.add(org)
        await s.flush()
        monitor = Monitor(
            organization_id=org.id,
            name="Nightly PostgreSQL Backup",
            ping_token=f"wcr_etest_{test_id}",
            schedule_type="cron",
            schedule_value="0 2 * * *",
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
            log_excerpt=(
                "ERROR pg_dump: write to file failed: ENOSPC\n"
                "FATAL: backup volume is full"
            ),
            failure_signature_hash="sha256:test-signature-abc",
        )
        s.add(run)
        await s.commit()
        ctx = {
            "org_id": org.id,
            "monitor_id": monitor.id,
            "run_id": run.id,
        }

    yield ctx

    async with db.session() as s:
        await s.execute(
            delete(AIExplanation).where(
                AIExplanation.organization_id == ctx["org_id"]
            )
        )
        await s.execute(
            delete(AuditLog).where(AuditLog.organization_id == ctx["org_id"])
        )
        await s.execute(delete(Run).where(Run.organization_id == ctx["org_id"]))
        await s.execute(delete(Monitor).where(Monitor.id == ctx["monitor_id"]))
        await s.execute(delete(Organization).where(Organization.id == ctx["org_id"]))
        await s.commit()


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_explain_failure_creates_row(
    seeded_failed_run: dict[str, uuid.UUID],
) -> None:
    fake = FakeAnthropic()
    expl_id = await explain_failure(seeded_failed_run["run_id"], client=fake)
    assert expl_id is not None

    async with db.session() as s:
        e = (
            await s.execute(
                select(AIExplanation).where(AIExplanation.id == expl_id)
            )
        ).scalar_one()

    assert e.prompt_version == PROMPT_VERSION
    assert e.model == settings.anthropic_model_default
    assert e.root_cause.startswith("Job failed because")
    assert "ENOSPC" in e.explanation or "ENOSPC" in e.root_cause
    assert e.suggested_fix
    assert e.confidence in {"high", "medium", "low"}
    assert e.input_tokens > 0
    assert e.output_tokens > 0
    assert e.cost_usd_micro > 0
    assert e.cached_from_signature_hash is None

    # Fake client should have received the call with caching enabled.
    assert len(fake.messages.calls) == 1
    call = fake.messages.calls[0]
    assert call["model"] == settings.anthropic_model_default
    system = call["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}


async def test_explain_failure_skips_non_failed_run(
    seeded_failed_run: dict[str, uuid.UUID],
) -> None:
    # Flip the run to succeeded and try to explain it — should no-op.
    async with db.session() as s:
        run = (
            await s.execute(
                select(Run).where(Run.id == seeded_failed_run["run_id"])
            )
        ).scalar_one()
        run.state = "succeeded"
        await s.commit()

    fake = FakeAnthropic()
    expl_id = await explain_failure(seeded_failed_run["run_id"], client=fake)
    assert expl_id is None
    assert len(fake.messages.calls) == 0


async def test_explain_failure_returns_none_for_unknown_run(
    connected_db: None,
) -> None:
    fake = FakeAnthropic()
    result = await explain_failure(uuid.uuid4(), client=fake)
    assert result is None
    assert len(fake.messages.calls) == 0


async def test_explain_failure_reuses_signature_hash_cache(
    seeded_failed_run: dict[str, uuid.UUID],
) -> None:
    """A second failed run with the same signature within 24h reuses the
    first explanation's content and never calls the API again."""
    ctx = seeded_failed_run
    fake_first = FakeAnthropic(
        text=(
            "Job failed because `pg_dump` returned ENOSPC.\n\n"
            "Volume hit 100% before archive finished.\n\n"
            "Rotate old backups or expand the volume."
        )
    )
    first_id = await explain_failure(ctx["run_id"], client=fake_first)
    assert first_id is not None

    # Add a second failed run with the same signature.
    async with db.session() as s:
        run2 = Run(
            organization_id=ctx["org_id"],
            monitor_id=ctx["monitor_id"],
            state="failed",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            exit_code=1,
            log_excerpt="another similar failure",
            failure_signature_hash="sha256:test-signature-abc",
        )
        s.add(run2)
        await s.commit()
        run2_id = run2.id

    fake_second = FakeAnthropic(text="DIFFERENT response that should be ignored")
    second_id = await explain_failure(run2_id, client=fake_second)
    assert second_id is not None
    # The second call must not have hit the API.
    assert len(fake_second.messages.calls) == 0

    async with db.session() as s:
        cached = (
            await s.execute(
                select(AIExplanation).where(AIExplanation.id == second_id)
            )
        ).scalar_one()
    assert cached.cached_from_signature_hash == "sha256:test-signature-abc"
    assert cached.input_tokens == 0
    assert cached.cost_usd_micro == 0
    assert "pg_dump" in cached.root_cause  # copied from the original


async def test_explain_failure_enforces_free_tier_quota(
    seeded_failed_run: dict[str, uuid.UUID],
) -> None:
    """At the 100/month free-tier ceiling, the API call is skipped and a
    quota-exhausted stub is persisted instead."""
    ctx = seeded_failed_run

    # Pre-fill the org with the quota's worth of explanations dated this month.
    async with db.session() as s:
        for _ in range(_FREE_TIER_MONTHLY_QUOTA):
            s.add(
                AIExplanation(
                    organization_id=ctx["org_id"],
                    run_id=ctx["run_id"],
                    prompt_version=PROMPT_VERSION,
                    model=settings.anthropic_model_default,
                    root_cause="seed",
                    explanation="seed",
                    suggested_fix="seed",
                    confidence="medium",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd_micro=0,
                )
            )
        await s.commit()

    fake = FakeAnthropic()
    expl_id = await explain_failure(ctx["run_id"], client=fake)
    assert expl_id is not None
    # No API call must have been made.
    assert len(fake.messages.calls) == 0

    async with db.session() as s:
        e = (
            await s.execute(
                select(AIExplanation).where(AIExplanation.id == expl_id)
            )
        ).scalar_one()
    assert e.model == "quota-exhausted"
    assert "free tier" in e.explanation.lower()
    assert e.cost_usd_micro == 0


async def test_ping_failed_enqueues_analyze_job(
    http_client: Any, seeded_monitor: dict[str, Any]
) -> None:
    """A failed ping should land a job on the analyze queue."""
    import redis
    from rq import Queue

    from apps.api.config import settings as cfg

    # Drain the analyze queue first so this test isn't polluted.
    sync_redis = redis.Redis.from_url(cfg.redis_url)
    Queue("analyze", connection=sync_redis).empty()

    r = await http_client.post(
        f"/p/{seeded_monitor['ping_token']}/fail",
        json={"exit_code": 1, "logs": "ERROR: test enqueue"},
    )
    assert r.status_code == 200

    q = Queue("analyze", connection=sync_redis)
    assert q.count == 1
    job = q.jobs[0]
    assert job.func_name == "apps.worker.tasks.analyze.analyze_run"

    # Clean up the queued job so other tests aren't affected.
    q.empty()
    sync_redis.close()


# ── Optional live test (gated on real API key) ───────────────────────────────


@pytest.mark.skipif(
    not settings.anthropic_api_key.startswith("sk-ant-"),
    reason="ANTHROPIC_API_KEY not configured — skipping live Anthropic call",
)
async def test_explain_failure_real_anthropic_call(
    seeded_failed_run: dict[str, uuid.UUID],
) -> None:
    """One real round-trip to Claude Haiku. Costs roughly a fraction of a
    cent. Skipped when no API key is configured."""
    expl_id = await explain_failure(seeded_failed_run["run_id"])
    assert expl_id is not None

    async with db.session() as s:
        e = (
            await s.execute(
                select(AIExplanation).where(AIExplanation.id == expl_id)
            )
        ).scalar_one()

    assert e.model == settings.anthropic_model_default
    assert e.root_cause
    assert e.explanation
    assert e.suggested_fix
    assert e.input_tokens > 0
    assert e.output_tokens > 0
    assert e.cost_usd_micro > 0
    # Claude was told the failure is ENOSPC / disk full — it should mention
    # at least one of "disk", "space", "ENOSPC", or "volume".
    blob = f"{e.root_cause} {e.explanation} {e.suggested_fix}".lower()
    assert any(kw in blob for kw in ("disk", "space", "enospc", "volume"))
