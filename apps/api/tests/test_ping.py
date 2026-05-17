"""Ping endpoint integration tests.

These exercise the full HTTP path through ``/p/{ping_token}`` against the
real Postgres + Redis in docker-compose. Each test gets its own freshly
seeded monitor (unique ping token + slug + UUID) and cleans up after.
"""
from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from apps.api.db import db
from apps.api.models import AuditLog, Run

# asyncio_mode=auto in pyproject.toml means async tests run on the event
# loop automatically; no module-level pytestmark needed.


async def test_ping_default_creates_succeeded_run(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    token = seeded_monitor["ping_token"]
    r = await http_client.post(f"/p/{token}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert data["run_id"]

    async with db.session() as s:
        runs = (
            await s.execute(
                select(Run).where(Run.monitor_id == seeded_monitor["monitor_id"])
            )
        ).scalars().all()
    assert len(runs) == 1
    assert runs[0].state == "succeeded"
    assert runs[0].ended_at is not None
    assert runs[0].started_at is None


async def test_ping_get_method_works(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    """``GET /p/{token}`` is the simplest curl form (CONTEXT.md §6.1)."""
    r = await http_client.get(f"/p/{seeded_monitor['ping_token']}")
    assert r.status_code == 200


async def test_ping_start_records_started_state(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    r = await http_client.post(f"/p/{seeded_monitor['ping_token']}/start")
    assert r.status_code == 200

    async with db.session() as s:
        run = (
            await s.execute(
                select(Run).where(Run.monitor_id == seeded_monitor["monitor_id"])
            )
        ).scalar_one()
    assert run.state == "started"
    assert run.started_at is not None
    assert run.ended_at is None


async def test_ping_fail_redacts_secrets_and_writes_signature(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    payload = {
        "exit_code": 1,
        "duration_ms": 5000,
        "logs": (
            "2026-05-10T18:00:00Z ERROR connecting to S3\n"
            "  using AKIAIOSFODNN7EXAMPLE / wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
            "  failed: AccessDenied"
        ),
        "metadata": {"host": "worker-01"},
    }
    r = await http_client.post(
        f"/p/{seeded_monitor['ping_token']}/fail", json=payload
    )
    assert r.status_code == 200

    async with db.session() as s:
        run = (
            await s.execute(
                select(Run).where(Run.monitor_id == seeded_monitor["monitor_id"])
            )
        ).scalar_one()

    assert run.state == "failed"
    assert run.exit_code == 1
    assert run.duration_ms == 5000
    assert run.metadata_json == {"host": "worker-01"}
    # Redaction
    assert run.log_excerpt is not None
    assert "AKIAIOSFODNN7EXAMPLE" not in run.log_excerpt
    assert "wJalrXUtnFEMI" not in run.log_excerpt
    assert "[REDACTED:aws_access_key]" in run.log_excerpt
    # Signature
    assert run.failure_signature_hash is not None
    assert run.failure_signature_hash.startswith("sha256:")


async def test_ping_idempotent_on_external_id(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    """Same external_id on the same monitor → exactly one row, second call
    returns ``status: duplicate`` with the original run_id."""
    token = seeded_monitor["ping_token"]
    ext = "ci-build-42"

    r1 = await http_client.post(f"/p/{token}/start/{ext}")
    r2 = await http_client.post(f"/p/{token}/start/{ext}")

    assert r1.status_code == 200
    assert r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    assert d1["status"] == "ok"
    assert d2["status"] == "duplicate"
    assert d1["run_id"] == d2["run_id"]

    async with db.session() as s:
        runs = (
            await s.execute(
                select(Run).where(Run.monitor_id == seeded_monitor["monitor_id"])
            )
        ).scalars().all()
    assert len(runs) == 1


async def test_ping_unknown_token_returns_404(
    http_client: AsyncClient, connected_db: None
) -> None:
    r = await http_client.post("/p/wcr_does_not_exist_zzz")
    assert r.status_code == 404


async def test_ping_oversized_payload_for_free_tier(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    """Free tier cap is 50KB. Anything larger must return 413."""
    big_logs = "X" * (60 * 1024)
    r = await http_client.post(
        f"/p/{seeded_monitor['ping_token']}/fail",
        json={"logs": big_logs},
    )
    assert r.status_code == 413


async def test_ping_invalid_state_returns_400(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    r = await http_client.post(f"/p/{seeded_monitor['ping_token']}/garglblaster")
    assert r.status_code == 400


async def test_ping_writes_audit_log_with_ip_and_user_agent(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    await http_client.post(
        f"/p/{seeded_monitor['ping_token']}",
        headers={"User-Agent": "WhycronTest/0.1"},
    )
    async with db.session() as s:
        audits = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.organization_id == seeded_monitor["org_id"],
                    AuditLog.action == "ping.recorded",
                )
            )
        ).scalars().all()
    assert len(audits) == 1
    assert audits[0].user_agent == "WhycronTest/0.1"
    assert audits[0].entity_type == "run"


async def test_ping_truncates_long_logs_server_side(
    http_client: AsyncClient, seeded_monitor: dict[str, Any]
) -> None:
    """Server-side log truncation keeps only the last N lines (CONTEXT.md §6.3)."""
    lines = [f"line {i}" for i in range(500)]
    payload = {"exit_code": 1, "logs": "\n".join(lines)}
    r = await http_client.post(
        f"/p/{seeded_monitor['ping_token']}/fail", json=payload
    )
    assert r.status_code == 200

    async with db.session() as s:
        run = (
            await s.execute(
                select(Run).where(Run.monitor_id == seeded_monitor["monitor_id"])
            )
        ).scalar_one()
    assert run.log_excerpt is not None
    # First lines should be gone; last lines should be present.
    assert "line 0\n" not in run.log_excerpt
    assert "line 499" in run.log_excerpt
    # Original size is recorded for billing/diagnostics.
    assert run.log_size_bytes is not None
    assert run.log_size_bytes > len(run.log_excerpt)
