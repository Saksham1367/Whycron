"""Account API tests — usage counters + per-tier limits."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.api.db import db
from apps.api.models import AIExplanation, Monitor


async def test_account_returns_user_and_org_basics(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    response = await client.get("/api/v1/account")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(ctx["user_id"])
    assert data["organization_id"] == str(ctx["org_id"])
    assert data["email"] == ctx["email"]
    assert data["role"] == "owner"
    assert data["tier"] == "free"


async def test_account_usage_counts_active_monitors(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    async with db.session() as s:
        for i in range(3):
            s.add(
                Monitor(
                    organization_id=ctx["org_id"],
                    name=f"M{i}",
                    ping_token=f"wcr_acct_{uuid.uuid4().hex[:10]}",
                    schedule_type="cron",
                    schedule_value="*/5 * * * *",
                )
            )
        await s.commit()
    response = await client.get("/api/v1/account")
    assert response.json()["usage"]["monitors_active"] == 3


async def test_account_usage_counts_explanations_this_month(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    async with db.session() as s:
        monitor = Monitor(
            organization_id=ctx["org_id"],
            name="m",
            ping_token=f"wcr_acct_{uuid.uuid4().hex[:10]}",
            schedule_type="cron",
            schedule_value="*/5 * * * *",
        )
        s.add(monitor)
        await s.flush()
        from apps.api.models import Run

        run = Run(
            organization_id=ctx["org_id"],
            monitor_id=monitor.id,
            state="failed",
            ended_at=datetime.now(timezone.utc),
        )
        s.add(run)
        await s.flush()
        for _ in range(4):
            s.add(
                AIExplanation(
                    organization_id=ctx["org_id"],
                    run_id=run.id,
                    prompt_version="v1",
                    model="claude-haiku-4-5-20251001",
                    root_cause="x",
                    explanation="y",
                    suggested_fix="z",
                    confidence="medium",
                    input_tokens=10,
                    output_tokens=5,
                    cost_usd_micro=60,
                )
            )
        await s.commit()
    response = await client.get("/api/v1/account")
    assert response.json()["usage"]["ai_explanations_this_month"] == 4


async def test_account_returns_correct_limits_for_free_tier(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    data = (await client.get("/api/v1/account")).json()
    assert data["usage"]["monitors_limit"] == 5
    assert data["usage"]["ai_explanations_monthly_limit"] == 100


async def test_account_unlimited_tier_returns_minus_one(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory(tier="enterprise")
    data = (await client.get("/api/v1/account")).json()
    assert data["usage"]["monitors_limit"] == -1
    assert data["usage"]["ai_explanations_monthly_limit"] == -1


async def test_account_requires_auth(http_client) -> None:
    response = await http_client.get("/api/v1/account")
    assert response.status_code == 401
