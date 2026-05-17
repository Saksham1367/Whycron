"""AI failure-explanation service (CONTEXT.md §8).

Pure function: given a failed ``Run.id``, generate and persist an
``AIExplanation`` row. Callable from the worker (``apps.worker.tasks.
analyze``) or directly in tests.

Three short-circuits sit in front of the Anthropic API call:

1. **Run validity** — non-existent or non-failed runs are no-ops.
2. **Free-tier quota** — orgs on the free tier get 100 explanations / month
   (CONTEXT.md §8.3). Past that, we persist a "quota exhausted" stub.
3. **Signature-hash dedup** — if any AIExplanation row in the same org has
   the same ``failure_signature_hash`` and was created within 24h, we copy
   its content instead of calling the API again.

Anthropic prompt caching is applied to the system prompt (5 min TTL). The
``last successful run logs`` block could also be cached per monitor; we
defer that to a later phase since per-monitor cache reuse within 5 min is
rare in practice.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import AIExplanation, Monitor, Organization, Run
from apps.api.services.ai_validator import grade_confidence

if TYPE_CHECKING:  # avoid importing anthropic at API import time
    from anthropic import AsyncAnthropic

log = structlog.get_logger("whycron.ai_explainer")

PROMPT_VERSION = "v1"
PROMPT_FILE = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "prompts"
    / f"failure-explanation-{PROMPT_VERSION}.md"
)

# Pricing for claude-haiku-4-5-20251001, USD per million tokens.
# TODO(saksham): verify against https://www.anthropic.com/pricing each quarter.
_HAIKU_INPUT_USD_PER_MTOK = 1.0
_HAIKU_OUTPUT_USD_PER_MTOK = 5.0
_HAIKU_CACHE_READ_USD_PER_MTOK = 0.1
_HAIKU_CACHE_WRITE_USD_PER_MTOK = 1.25

_FREE_TIER_MONTHLY_QUOTA = 100
_FAILED_LOG_CHAR_BUDGET = 12_000   # ~3000 tokens
_SUCCESS_LOG_CHAR_BUDGET = 4_000   # ~1000 tokens
_MAX_OUTPUT_TOKENS = 400
_DEDUP_WINDOW_HOURS = 24


# ── Public API ────────────────────────────────────────────────────────────────


async def explain_failure(
    run_id: uuid.UUID,
    *,
    session: AsyncSession | None = None,
    client: Any | None = None,
) -> uuid.UUID | None:
    """Generate and persist an explanation for ``run_id``.

    Returns the new ``AIExplanation.id`` on success, or ``None`` if the run
    doesn't exist or isn't in the ``failed`` state.

    ``session`` and ``client`` are injection points for tests; production
    callers leave them None and the function manages its own connections.
    """
    if session is not None:
        expl_id = await _explain_inner(session, run_id, client)
    else:
        async with db.session() as s:
            expl_id = await _explain_inner(s, run_id, client)
    if expl_id is not None:
        # Single fan-out point — covers the LLM, cached, and quota-exhausted
        # paths uniformly. Failure here must not break the explainer.
        _enqueue_notify_safe(run_id)
    return expl_id


# ── Inner implementation ──────────────────────────────────────────────────────


async def _explain_inner(
    session: AsyncSession,
    run_id: uuid.UUID,
    client: Any | None,
) -> uuid.UUID | None:
    run = (
        await session.execute(select(Run).where(Run.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        log.warning("run_not_found", run_id=str(run_id))
        return None
    if run.state != "failed":
        log.info(
            "skipping_non_failed_run", run_id=str(run_id), state=run.state
        )
        return None

    # Capture primitives before any commit/rollback could expire the row.
    org_id = run.organization_id
    monitor_id = run.monitor_id
    signature = run.failure_signature_hash
    exit_code = run.exit_code
    duration_ms = run.duration_ms
    failed_log = run.log_excerpt or ""

    monitor = (
        await session.execute(select(Monitor).where(Monitor.id == monitor_id))
    ).scalar_one()
    monitor_name = monitor.name
    monitor_schedule = monitor.schedule_value
    monitor_tz = monitor.timezone

    tier = (
        await session.execute(
            select(Organization.tier).where(Organization.id == org_id)
        )
    ).scalar_one_or_none() or "free"

    # 1. Free-tier quota gate.
    if tier == "free":
        used = await _count_monthly_explanations(session, org_id)
        if used >= _FREE_TIER_MONTHLY_QUOTA:
            log.info(
                "free_tier_quota_exhausted",
                org_id=str(org_id),
                used=used,
            )
            return await _persist_quota_exhausted(
                session, org_id, run_id, monitor_name, exit_code
            )

    # 2. Signature-hash dedup.
    if signature:
        cached = await _find_recent_cached(session, org_id, signature, run_id)
        if cached is not None:
            log.info(
                "explanation_cache_hit",
                run_id=str(run_id),
                signature=signature,
            )
            return await _persist_cached(session, org_id, run_id, signature, cached)

    # 3. Real LLM call.
    last_success_logs = await _load_last_success_logs(session, monitor_id)
    stats = await _load_recent_run_stats(session, monitor_id)
    user_context = _build_user_context(
        monitor_name=monitor_name,
        schedule_value=monitor_schedule,
        timezone_name=monitor_tz,
        stats=stats,
        duration_ms=duration_ms,
        last_success_logs=last_success_logs,
        failed_log=failed_log,
        exit_code=exit_code,
    )

    client = client or _get_default_client()
    response = await client.messages.create(
        model=settings.anthropic_model_default,
        max_tokens=_MAX_OUTPUT_TOKENS,
        system=[
            {
                "type": "text",
                "text": _system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_context}],
    )

    raw_text = response.content[0].text
    parsed = _parse_three_paragraphs(raw_text)
    confidence = grade_confidence(raw_text, user_context)

    usage = response.usage
    input_tok = (getattr(usage, "input_tokens", 0) or 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    output_tok = getattr(usage, "output_tokens", 0) or 0
    total_input = input_tok + cache_read + cache_write
    cost = _compute_cost_micro(input_tok, output_tok, cache_read, cache_write)

    explanation = AIExplanation(
        organization_id=org_id,
        run_id=run_id,
        prompt_version=PROMPT_VERSION,
        model=settings.anthropic_model_default,
        root_cause=parsed["root_cause"],
        explanation=parsed["explanation"],
        suggested_fix=parsed["suggested_fix"],
        confidence=confidence,
        input_tokens=total_input,
        output_tokens=output_tok,
        cost_usd_micro=cost,
    )
    session.add(explanation)
    await session.commit()
    return explanation.id


# ── Quota + dedup helpers ─────────────────────────────────────────────────────


async def _count_monthly_explanations(
    session: AsyncSession, org_id: uuid.UUID
) -> int:
    now = datetime.now(timezone.utc)
    month_start = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    stmt = select(func.count(AIExplanation.id)).where(
        AIExplanation.organization_id == org_id,
        AIExplanation.created_at >= month_start,
    )
    return int((await session.execute(stmt)).scalar_one())


async def _find_recent_cached(
    session: AsyncSession,
    org_id: uuid.UUID,
    signature: str,
    current_run_id: uuid.UUID,
) -> AIExplanation | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_DEDUP_WINDOW_HOURS)
    stmt = (
        select(AIExplanation)
        .join(Run, Run.id == AIExplanation.run_id)
        .where(
            AIExplanation.organization_id == org_id,
            Run.failure_signature_hash == signature,
            AIExplanation.created_at >= cutoff,
            AIExplanation.run_id != current_run_id,
            # Don't chain caches — copy from an original explanation only.
            AIExplanation.cached_from_signature_hash.is_(None),
        )
        .order_by(AIExplanation.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _persist_cached(
    session: AsyncSession,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    signature: str,
    source: AIExplanation,
) -> uuid.UUID:
    explanation = AIExplanation(
        organization_id=org_id,
        run_id=run_id,
        prompt_version=source.prompt_version,
        model=source.model,
        root_cause=source.root_cause,
        explanation=source.explanation,
        suggested_fix=source.suggested_fix,
        confidence=source.confidence,
        input_tokens=0,
        output_tokens=0,
        cost_usd_micro=0,
        cached_from_signature_hash=signature,
    )
    session.add(explanation)
    await session.commit()
    return explanation.id


async def _persist_quota_exhausted(
    session: AsyncSession,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    monitor_name: str,
    exit_code: int | None,
) -> uuid.UUID:
    explanation = AIExplanation(
        organization_id=org_id,
        run_id=run_id,
        prompt_version=PROMPT_VERSION,
        model="quota-exhausted",
        root_cause=(
            f"Job '{monitor_name}' failed"
            + (f" with exit code {exit_code}." if exit_code is not None else ".")
        ),
        explanation=(
            "The free tier's monthly limit of 100 AI explanations has been "
            "reached for this organization. The run is recorded normally; "
            "automated explanations resume next month or with a paid plan."
        ),
        suggested_fix=(
            "Upgrade to Pro for unlimited explanations, or review the "
            "stored failure logs for this run directly in the dashboard."
        ),
        confidence="low",
        input_tokens=0,
        output_tokens=0,
        cost_usd_micro=0,
    )
    session.add(explanation)
    await session.commit()
    return explanation.id


# ── Context construction ─────────────────────────────────────────────────────


async def _load_last_success_logs(
    session: AsyncSession, monitor_id: uuid.UUID
) -> str | None:
    stmt = (
        select(Run.log_excerpt)
        .where(
            Run.monitor_id == monitor_id,
            Run.state == "succeeded",
            Run.log_excerpt.is_not(None),
        )
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _load_recent_run_stats(
    session: AsyncSession, monitor_id: uuid.UUID
) -> dict[str, Any]:
    subq = (
        select(Run.state, Run.duration_ms)
        .where(Run.monitor_id == monitor_id)
        .order_by(Run.created_at.desc())
        .limit(7)
        .subquery()
    )
    rows = (
        await session.execute(select(subq.c.state, subq.c.duration_ms))
    ).all()
    succeeded = sum(1 for r in rows if r.state == "succeeded")
    failed = sum(1 for r in rows if r.state == "failed")
    missed = sum(1 for r in rows if r.state == "missed")
    durations = [r.duration_ms for r in rows if r.duration_ms is not None]
    avg = int(sum(durations) / len(durations)) if durations else None
    return {
        "succeeded": succeeded,
        "failed": failed,
        "missed": missed,
        "avg_duration_ms": avg,
    }


def _build_user_context(
    *,
    monitor_name: str,
    schedule_value: str,
    timezone_name: str,
    stats: dict[str, Any],
    duration_ms: int | None,
    last_success_logs: str | None,
    failed_log: str,
    exit_code: int | None,
) -> str:
    """Compose the JOB METADATA block per CONTEXT.md §8.2."""
    success_block = (last_success_logs or "(no prior successful run)")[
        -_SUCCESS_LOG_CHAR_BUDGET:
    ]
    failed_block = failed_log[-_FAILED_LOG_CHAR_BUDGET:] or "(no logs attached)"
    return (
        "JOB METADATA:\n"
        f"Name: {monitor_name}\n"
        f"Schedule: {schedule_value} ({timezone_name})\n"
        f"Last 7 runs: {stats['succeeded']} success, "
        f"{stats['missed']} missed, "
        f"{stats['failed']} fail (this one)\n"
        f"Average runtime (ms): {stats['avg_duration_ms'] or 'n/a'}\n"
        f"This run runtime (ms): {duration_ms or 'n/a'}\n"
        "\n"
        "LAST SUCCESSFUL RUN LOGS (last lines, redacted):\n"
        f"{success_block}\n"
        "\n"
        "THIS FAILED RUN LOGS (last lines, redacted):\n"
        f"{failed_block}\n"
        "\n"
        f"EXIT CODE: {exit_code if exit_code is not None else 'n/a'}\n"
    )


# ── Parsing + pricing ────────────────────────────────────────────────────────


def _parse_three_paragraphs(text: str) -> dict[str, str]:
    """Split Claude's 3-paragraph output (CONTEXT.md §8.1)."""
    blocks = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    if len(blocks) < 3:
        # Fall back to line-by-line if Claude omitted blank-line separators.
        blocks = [p.strip() for p in text.strip().splitlines() if p.strip()]
    if len(blocks) >= 3:
        return {
            "root_cause": blocks[0],
            "explanation": blocks[1],
            "suggested_fix": blocks[2],
        }
    return {
        "root_cause": text.strip() or "(empty response)",
        "explanation": "",
        "suggested_fix": "",
    }


def _compute_cost_micro(
    input_tok: int, output_tok: int, cache_read: int, cache_write: int
) -> int:
    """Return cost in microUSD. ``USD_per_MTok`` × tokens equals microUSD."""
    micro = (
        input_tok * _HAIKU_INPUT_USD_PER_MTOK
        + output_tok * _HAIKU_OUTPUT_USD_PER_MTOK
        + cache_read * _HAIKU_CACHE_READ_USD_PER_MTOK
        + cache_write * _HAIKU_CACHE_WRITE_USD_PER_MTOK
    )
    return int(micro)


# ── Prompt + client ──────────────────────────────────────────────────────────


_SYSTEM_PROMPT_CACHE: str | None = None


def _system_prompt() -> str:
    """Read the prompt body from the versioned markdown file (once)."""
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is None:
        text = PROMPT_FILE.read_text(encoding="utf-8")
        start = text.find("```\n")
        if start == -1:
            raise RuntimeError(
                f"Prompt file {PROMPT_FILE} is missing the opening code fence"
            )
        end = text.find("```", start + 4)
        if end == -1:
            raise RuntimeError(
                f"Prompt file {PROMPT_FILE} is missing the closing code fence"
            )
        _SYSTEM_PROMPT_CACHE = text[start + 4 : end].strip()
    return _SYSTEM_PROMPT_CACHE


def _get_default_client() -> "AsyncAnthropic":
    """Lazy import — ``anthropic`` is in the worker extra, not the api extra."""
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _enqueue_notify_safe(run_id: uuid.UUID) -> None:
    """Best-effort: enqueue a notify job for this run. Failure to enqueue
    must not break the explainer (the run + explanation are already
    durably stored)."""
    try:
        from apps.api.services.queue import enqueue_notify_run

        enqueue_notify_run(run_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("notify_enqueue_failed", run_id=str(run_id), error=str(exc))
