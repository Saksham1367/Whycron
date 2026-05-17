"""The ping endpoint — the hot write path.

Target: <50ms p99 (CONTEXT.md §6.3). Every other path can wait; this one
cannot. The handler does the minimum necessary work synchronously:

1. Look up the monitor by ping token.
2. Apply the per-monitor sliding-window rate limit.
3. Read the body, enforce the per-tier size cap.
4. Truncate the log excerpt server-side.
5. Run the redactor on the excerpt before storage.
6. Compute the failure signature hash if state == failed.
7. Insert the run row, idempotent on (monitor_id, run_external_id).
8. Insert one audit-log row.
9. Return 200.

URL shapes (CONTEXT.md §6.1):

    GET/POST /p/{ping_token}                        succeeded
    GET/POST /p/{ping_token}/{run_state}            run_state, no external id
    GET/POST /p/{ping_token}/{run_state}/{ext_id}   run_state with external id

CONTEXT.md §4.2.10 + the ``idx_runs_dedup`` partial unique index together
guarantee that retried pings with the same ``run_external_id`` create at
most one row.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import db
from apps.api.models import AuditLog, Monitor, Organization, Run
from apps.api.services.queue import enqueue_analyze_run
from apps.api.services.ratelimit import check_ping_rate_limit
from apps.api.services.redactor import redact
from apps.api.services.signature import signature_hash

router = APIRouter(tags=["ping"])
log = structlog.get_logger("whycron.ping")

# URL state shorthand → internal Run.state value.
_STATE_ALIASES: dict[str, str] = {
    "start": "started",
    "started": "started",
    "success": "succeeded",
    "succeeded": "succeeded",
    "ok": "succeeded",
    "fail": "failed",
    "failed": "failed",
    "error": "failed",
}

_PAYLOAD_CAP_FREE = 50 * 1024
_PAYLOAD_CAP_PAID = 500 * 1024
_LOG_LINE_CAP = 200
_LOG_BYTES_CAP = 50 * 1024


class PingPayload(BaseModel):
    """Optional JSON body that may accompany a POST ping."""

    model_config = ConfigDict(extra="ignore")

    exit_code: int | None = None
    duration_ms: int | None = None
    logs: str | None = None
    metadata: dict[str, Any] | None = None


def _resolve_state(raw: str) -> str:
    state = _STATE_ALIASES.get(raw.lower())
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown run state: {raw!r}",
        )
    return state


def _truncate_logs(text: str) -> str:
    """Keep only the last ``_LOG_LINE_CAP`` lines and clamp total bytes."""
    lines = text.splitlines()[-_LOG_LINE_CAP:]
    truncated = "\n".join(lines)
    if len(truncated.encode("utf-8")) > _LOG_BYTES_CAP:
        truncated = truncated.encode("utf-8")[-_LOG_BYTES_CAP:].decode(
            "utf-8", errors="ignore"
        )
    return truncated


async def _read_payload(request: Request, tier: str) -> PingPayload:
    if request.method == "GET":
        return PingPayload()
    cap = _PAYLOAD_CAP_FREE if tier == "free" else _PAYLOAD_CAP_PAID

    cl_header = request.headers.get("content-length")
    if cl_header is not None:
        try:
            if int(cl_header) > cap:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Payload too large",
                )
        except ValueError:
            pass  # garbage header, fall through to body length check

    body = await request.body()
    if len(body) > cap:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Payload too large",
        )
    if not body:
        return PingPayload()
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        ) from exc
    if not isinstance(data, dict):
        return PingPayload()
    return PingPayload(**data)


async def _load_monitor(session: AsyncSession, ping_token: str) -> Monitor:
    stmt = select(Monitor).where(
        Monitor.ping_token == ping_token,
        Monitor.deleted_at.is_(None),
    )
    monitor = (await session.execute(stmt)).scalar_one_or_none()
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitor not found",
        )
    return monitor


async def _load_org_tier(
    session: AsyncSession, organization_id: uuid.UUID
) -> str:
    stmt = select(Organization.tier).where(Organization.id == organization_id)
    tier = (await session.execute(stmt)).scalar_one_or_none()
    return tier or "free"


async def _record_ping(
    ping_token: str,
    state: str,
    external_id: str | None,
    request: Request,
) -> dict[str, str]:
    async with db.session() as session:
        monitor = await _load_monitor(session, ping_token)
        # Capture primitives before any flush — ``session.rollback()`` on the
        # idempotency path would expire the ORM instance, and lazy-loading
        # ``monitor.id`` after that triggers a sync attribute fetch outside
        # any greenlet context (MissingGreenlet error).
        monitor_id = monitor.id
        monitor_org_id = monitor.organization_id

        tier = await _load_org_tier(session, monitor_org_id)
        await check_ping_rate_limit(monitor_id, tier)

        payload = await _read_payload(request, tier)

        original_log_bytes = (
            len(payload.logs.encode("utf-8")) if payload.logs else None
        )
        log_excerpt: str | None = None
        if payload.logs:
            log_excerpt = redact(_truncate_logs(payload.logs))

        now = datetime.now(timezone.utc)
        run = Run(
            organization_id=monitor_org_id,
            monitor_id=monitor_id,
            run_external_id=external_id,
            state=state,
            started_at=now if state == "started" else None,
            ended_at=now if state != "started" else None,
            duration_ms=payload.duration_ms,
            exit_code=payload.exit_code,
            log_excerpt=log_excerpt,
            log_size_bytes=original_log_bytes,
            failure_signature_hash=(
                signature_hash(payload.exit_code, log_excerpt)
                if state == "failed"
                else None
            ),
            metadata_json=payload.metadata or {},
        )
        session.add(run)

        try:
            await session.flush()
        except IntegrityError:
            # Duplicate (monitor_id, external_id). Idempotent — return the
            # already-recorded run's ID.
            await session.rollback()
            existing = (
                await session.execute(
                    select(Run.id).where(
                        Run.monitor_id == monitor_id,
                        Run.run_external_id == external_id,
                    )
                )
            ).scalar_one()
            return {"status": "duplicate", "run_id": str(existing)}

        run_id = run.id

        # Audit log — IP and user-agent for abuse detection (§6.3).
        client_ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:500] or None
        session.add(
            AuditLog(
                organization_id=monitor_org_id,
                action="ping.recorded",
                entity_type="run",
                entity_id=run_id,
                ip_address=client_ip,
                user_agent=ua,
            )
        )

        await session.commit()

    # Enqueue analysis job after the run is durably stored. Best-effort:
    # if Redis is unreachable here, the run is still recorded and a later
    # sweeper (Phase 4) will pick up unanalyzed failures.
    if state == "failed":
        try:
            await asyncio.to_thread(enqueue_analyze_run, run_id)
        except Exception as exc:
            log.warning(
                "analyze_enqueue_failed",
                error=str(exc),
                run_id=str(run_id),
            )

    return {"status": "ok", "run_id": str(run_id)}


# ── Three route shapes per CONTEXT.md §6.1 ───────────────────────────────────


@router.api_route("/p/{ping_token}", methods=["GET", "POST"])
async def ping_default(
    ping_token: str, request: Request
) -> dict[str, str]:
    return await _record_ping(ping_token, "succeeded", None, request)


@router.api_route("/p/{ping_token}/{run_state}", methods=["GET", "POST"])
async def ping_state(
    ping_token: str, run_state: str, request: Request
) -> dict[str, str]:
    return await _record_ping(
        ping_token, _resolve_state(run_state), None, request
    )


@router.api_route(
    "/p/{ping_token}/{run_state}/{external_id}", methods=["GET", "POST"]
)
async def ping_state_extid(
    ping_token: str,
    run_state: str,
    external_id: str,
    request: Request,
) -> dict[str, str]:
    return await _record_ping(
        ping_token, _resolve_state(run_state), external_id, request
    )
