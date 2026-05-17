"""Runs API tests — list/get/feedback + multi-tenancy."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from apps.api.db import db
from apps.api.models import AIExplanation, Monitor, Run


async def _seed_monitor_and_runs(
    org_id: uuid.UUID,
    states: list[str],
    *,
    with_explanation_on_index: int | None = None,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Insert a monitor + one run per state. Optionally attach an
    AIExplanation to the run at index ``with_explanation_on_index``.
    Returns ``(monitor_id, run_ids_in_insertion_order)``."""
    async with db.session() as s:
        monitor = Monitor(
            organization_id=org_id,
            name="Test Monitor",
            ping_token=f"wcr_test_{uuid.uuid4().hex[:10]}",
            schedule_type="cron",
            schedule_value="*/5 * * * *",
        )
        s.add(monitor)
        await s.flush()
        run_ids: list[uuid.UUID] = []
        for state in states:
            now = datetime.now(timezone.utc)
            run = Run(
                organization_id=org_id,
                monitor_id=monitor.id,
                state=state,
                started_at=now if state == "started" else None,
                ended_at=now if state != "started" else None,
                exit_code=1 if state == "failed" else None,
                log_excerpt="some log" if state == "failed" else None,
            )
            s.add(run)
            await s.flush()
            run_ids.append(run.id)
        if with_explanation_on_index is not None:
            target_run_id = run_ids[with_explanation_on_index]
            s.add(
                AIExplanation(
                    organization_id=org_id,
                    run_id=target_run_id,
                    prompt_version="v1",
                    model="claude-haiku-4-5-20251001",
                    root_cause="Job failed because something broke.",
                    explanation="Details here.",
                    suggested_fix="Try restarting.",
                    confidence="medium",
                    input_tokens=100,
                    output_tokens=50,
                    cost_usd_micro=600,
                )
            )
        await s.commit()
        return monitor.id, run_ids


async def test_list_runs_returns_only_own_org(authed_user_factory) -> None:
    client_a, ctx_a = await authed_user_factory()
    client_b, ctx_b = await authed_user_factory()
    await _seed_monitor_and_runs(ctx_a["org_id"], ["succeeded", "failed"])
    await _seed_monitor_and_runs(ctx_b["org_id"], ["failed", "missed"])

    a_resp = await client_a.get("/api/v1/runs")
    b_resp = await client_b.get("/api/v1/runs")
    assert a_resp.json()["total"] == 2
    assert b_resp.json()["total"] == 2

    a_monitor_ids = {r["monitor_id"] for r in a_resp.json()["items"]}
    b_monitor_ids = {r["monitor_id"] for r in b_resp.json()["items"]}
    assert a_monitor_ids.isdisjoint(b_monitor_ids)


async def test_list_runs_filters_by_state(authed_user_factory) -> None:
    client, ctx = await authed_user_factory()
    await _seed_monitor_and_runs(
        ctx["org_id"], ["succeeded", "failed", "missed", "succeeded"]
    )
    response = await client.get("/api/v1/runs?state=failed")
    assert response.json()["total"] == 1


async def test_list_runs_filters_by_monitor_id(authed_user_factory) -> None:
    client, ctx = await authed_user_factory()
    m1, _ = await _seed_monitor_and_runs(ctx["org_id"], ["succeeded"])
    m2, _ = await _seed_monitor_and_runs(ctx["org_id"], ["failed", "failed"])
    response = await client.get(f"/api/v1/runs?monitor_id={m2}")
    assert response.json()["total"] == 2
    for item in response.json()["items"]:
        assert item["monitor_id"] == str(m2)


async def test_get_run_returns_run_with_explanation(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    _, run_ids = await _seed_monitor_and_runs(
        ctx["org_id"], ["failed"], with_explanation_on_index=0
    )
    response = await client.get(f"/api/v1/runs/{run_ids[0]}")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "failed"
    assert data["explanation"]["root_cause"].startswith("Job failed")


async def test_get_run_without_explanation_returns_null(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    _, run_ids = await _seed_monitor_and_runs(ctx["org_id"], ["succeeded"])
    response = await client.get(f"/api/v1/runs/{run_ids[0]}")
    assert response.status_code == 200
    assert response.json()["explanation"] is None


async def test_get_run_404_for_other_org(authed_user_factory) -> None:
    client_a, ctx_a = await authed_user_factory()
    client_b, _ = await authed_user_factory()
    _, run_ids = await _seed_monitor_and_runs(ctx_a["org_id"], ["failed"])
    response = await client_b.get(f"/api/v1/runs/{run_ids[0]}")
    assert response.status_code == 404


async def test_feedback_records_value_on_explanation(
    authed_user_factory,
) -> None:
    client, ctx = await authed_user_factory()
    _, run_ids = await _seed_monitor_and_runs(
        ctx["org_id"], ["failed"], with_explanation_on_index=0
    )
    response = await client.post(
        f"/api/v1/runs/{run_ids[0]}/feedback",
        json={"feedback": "helpful"},
    )
    assert response.status_code == 204

    # Confirm via GET.
    detail = await client.get(f"/api/v1/runs/{run_ids[0]}")
    assert detail.json()["explanation"]["user_feedback"] == "helpful"


async def test_feedback_404_when_no_explanation(authed_user_factory) -> None:
    client, ctx = await authed_user_factory()
    _, run_ids = await _seed_monitor_and_runs(ctx["org_id"], ["failed"])
    response = await client.post(
        f"/api/v1/runs/{run_ids[0]}/feedback",
        json={"feedback": "not_helpful"},
    )
    assert response.status_code == 404


async def test_feedback_404_for_other_org(authed_user_factory) -> None:
    client_a, ctx_a = await authed_user_factory()
    client_b, _ = await authed_user_factory()
    _, run_ids = await _seed_monitor_and_runs(
        ctx_a["org_id"], ["failed"], with_explanation_on_index=0
    )
    response = await client_b.post(
        f"/api/v1/runs/{run_ids[0]}/feedback",
        json={"feedback": "helpful"},
    )
    assert response.status_code == 404


async def test_feedback_rejects_invalid_value(authed_user_factory) -> None:
    client, ctx = await authed_user_factory()
    _, run_ids = await _seed_monitor_and_runs(
        ctx["org_id"], ["failed"], with_explanation_on_index=0
    )
    response = await client.post(
        f"/api/v1/runs/{run_ids[0]}/feedback",
        json={"feedback": "amazing"},
    )
    assert response.status_code == 422
