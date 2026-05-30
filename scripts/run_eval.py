"""Whycron AI-explainer eval harness.

Loads ``docs/eval/failure-cases-v1.json``, replays each case through the
current production prompt against Anthropic's API, and grades the output
against the per-case ``must_contain`` / ``must_not_contain`` criteria.

This is the regression gate for any prompt change. CONTEXT.md §8.4
mitigation #2: "before any prompt change ships, run against the eval
set. All must still produce acceptable outputs."

Usage:
    uv run python scripts/run_eval.py
    uv run python scripts/run_eval.py --case db-backup-disk-full-001
    uv run python scripts/run_eval.py --category etl --verbose

Exit codes:
    0   every selected case passed
    1   one or more cases failed
    2   configuration error (missing ANTHROPIC_API_KEY, missing file, etc.)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# This script lives outside the FastAPI request lifecycle, so it imports the
# explainer module just to reuse the prompt and parser — it does NOT hit the
# database. We construct the user context from the eval JSON directly.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.config import settings  # noqa: E402
from apps.api.services.ai_explainer import (  # noqa: E402
    PROMPT_VERSION,
    _parse_v2_json,
    _system_prompt,
)
from apps.api.services.ai_validator import grade_confidence  # noqa: E402

EVAL_FILE = ROOT / "docs" / "eval" / "failure-cases-v1.json"
MAX_OUTPUT_TOKENS = 400


# ── Score model ──────────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    missing_required: list[str]
    found_forbidden: list[str]
    confidence: str
    raw_output: str
    cost_usd_micro: int
    # v2 additions — empty strings mean "case did not specify"
    expected_patch_kind: str
    actual_patch_kind: str


# ── Building the user context (mirrors ai_explainer._build_user_context) ────


def build_user_context(case: dict) -> str:
    """Compose the JOB METADATA + logs block in the same shape ai_explainer
    produces at runtime. The eval JSON already approximates this; we just
    format it consistently.
    """
    inp = case["input"]
    return (
        "JOB METADATA:\n"
        f"Name: {inp['monitor_name']}\n"
        f"Schedule: {inp['schedule']} ({inp.get('timezone', 'UTC')})\n"
        f"This run runtime (ms): {inp.get('duration_ms', 'n/a')}\n"
        "\n"
        "LAST SUCCESSFUL RUN LOGS (last lines, redacted):\n"
        f"{inp.get('logs_last_success') or '(no prior successful run)'}\n"
        "\n"
        "THIS FAILED RUN LOGS (last lines, redacted):\n"
        f"{inp.get('logs_failed') or '(no logs attached)'}\n"
        "\n"
        f"EXIT CODE: {inp.get('exit_code', 'n/a')}\n"
    )


# ── Calling Anthropic ────────────────────────────────────────────────────────


async def explain(case: dict, client) -> tuple[str, int]:
    """Send the case through the current v1 system prompt. Returns
    (raw response text, cost in microUSD)."""
    user_context = build_user_context(case)
    response = await client.messages.create(
        model=settings.anthropic_model_default,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=[
            {
                "type": "text",
                "text": _system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_context}],
    )
    text = response.content[0].text
    usage = response.usage
    cost = _compute_cost_micro(
        input_tok=getattr(usage, "input_tokens", 0) or 0,
        output_tok=getattr(usage, "output_tokens", 0) or 0,
        cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )
    return text, cost


def _compute_cost_micro(
    input_tok: int, output_tok: int, cache_read: int, cache_write: int
) -> int:
    # Same rates as apps/api/services/ai_explainer.py — kept inline so this
    # script stays standalone.
    micro = (
        input_tok * 1.0
        + output_tok * 5.0
        + cache_read * 0.1
        + cache_write * 1.25
    )
    return int(micro)


# ── Scoring a single case ────────────────────────────────────────────────────


def score_case(case: dict, raw_output: str) -> CaseResult:
    parsed = _parse_v2_json(raw_output)
    combined = " ".join(
        [
            parsed["root_cause"],
            parsed["explanation"],
            parsed["suggested_fix"] or "",
        ]
    ).lower()

    criteria = case.get("evaluation_criteria", {})
    must_contain = [c.lower() for c in criteria.get("must_contain", [])]
    must_contain_any_of = [
        c.lower() for c in criteria.get("must_contain_any_of", [])
    ]
    must_not_contain = [c.lower() for c in criteria.get("must_not_contain", [])]

    missing_required = [c for c in must_contain if c not in combined]
    # OR-gate: at least one of the listed alternatives must appear. Use
    # when several phrasings are all valid fixes for the same underlying
    # problem (e.g., "timezone" vs "after 21:00 UTC" for a scheduling bug).
    if must_contain_any_of and not any(c in combined for c in must_contain_any_of):
        missing_required.append(f"(none of: {must_contain_any_of})")

    found_forbidden = [c for c in must_not_contain if c in combined]

    # v2 patch-kind gate. If the case specifies an expected patch_kind,
    # the LLM's pick must match exactly — that's the whole point of the
    # structured output.
    expected_patch_kind = criteria.get("expected_patch_kind", "")
    actual_patch_kind = parsed.get("patch_kind", "")
    if expected_patch_kind and actual_patch_kind != expected_patch_kind:
        missing_required.append(
            f"patch_kind expected={expected_patch_kind!r} "
            f"got={actual_patch_kind!r}"
        )

    confidence = grade_confidence(raw_output, build_user_context(case))

    return CaseResult(
        case_id=case["case_id"],
        category=case["category"],
        passed=(not missing_required and not found_forbidden),
        missing_required=missing_required,
        found_forbidden=found_forbidden,
        confidence=confidence,
        raw_output=raw_output,
        cost_usd_micro=0,  # set by caller
        expected_patch_kind=expected_patch_kind,
        actual_patch_kind=actual_patch_kind,
    )


# ── Main ─────────────────────────────────────────────────────────────────────


async def run(
    *,
    case_id_filter: str | None,
    category_filter: str | None,
    verbose: bool,
) -> int:
    if not settings.anthropic_api_key.startswith("sk-ant-"):
        print(
            "FATAL: ANTHROPIC_API_KEY is not configured. The eval harness "
            "calls the real API; set the key in .env before running.",
            file=sys.stderr,
        )
        return 2

    if not EVAL_FILE.exists():
        print(f"FATAL: eval file not found at {EVAL_FILE}", file=sys.stderr)
        return 2

    payload = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if case_id_filter:
        cases = [c for c in cases if c["case_id"] == case_id_filter]
    if category_filter:
        cases = [c for c in cases if c["category"] == category_filter]
    if not cases:
        print("No cases matched the filter.", file=sys.stderr)
        return 2

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    results: list[CaseResult] = []
    total_cost_micro = 0

    print(f"Running {len(cases)} eval cases against prompt {PROMPT_VERSION}...\n")
    for case in cases:
        try:
            raw, cost = await explain(case, client)
        except Exception as exc:  # noqa: BLE001
            print(f"  {case['case_id']:40s}  ERROR  {exc!r}")
            results.append(
                CaseResult(
                    case_id=case["case_id"],
                    category=case["category"],
                    passed=False,
                    missing_required=["(API call failed)"],
                    found_forbidden=[],
                    confidence="low",
                    raw_output=f"API error: {exc!r}",
                    cost_usd_micro=0,
                    expected_patch_kind=(
                        case.get("evaluation_criteria", {})
                        .get("expected_patch_kind", "")
                    ),
                    actual_patch_kind="",
                )
            )
            continue

        result = score_case(case, raw)
        result.cost_usd_micro = cost
        total_cost_micro += cost
        results.append(result)

        marker = "PASS" if result.passed else "FAIL"
        patch_cell = (
            f"{result.actual_patch_kind or '-':14s}"
            if result.expected_patch_kind == result.actual_patch_kind
            else f"{result.actual_patch_kind or '-':>14}/{result.expected_patch_kind}"
        )
        print(
            f"  {result.case_id:40s}  {marker}  "
            f"conf={result.confidence:6s}  "
            f"patch={patch_cell}  "
            f"${result.cost_usd_micro / 1_000_000:.4f}"
        )
        if not result.passed:
            if result.missing_required:
                print(
                    f"      missing required: {result.missing_required}"
                )
            if result.found_forbidden:
                print(
                    f"      contained forbidden: {result.found_forbidden}"
                )
            if verbose:
                print("      --- output ---")
                for line in result.raw_output.splitlines():
                    print(f"      {line}")
                print("      ---")

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    print(
        f"\n{passed} / {len(results)} passed | "
        f"total cost ${total_cost_micro / 1_000_000:.4f}"
    )
    if failed:
        print(f"{failed} failed:")
        for r in results:
            if not r.passed:
                print(f"  - {r.case_id}")
    return 0 if failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Whycron AI-explainer eval harness"
    )
    parser.add_argument(
        "--case", dest="case_id", help="run a single case by ID"
    )
    parser.add_argument(
        "--category",
        help="run cases in a single category (db_backup, etl, etc.)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print full LLM output on failures",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(
        run(
            case_id_filter=args.case_id,
            category_filter=args.category,
            verbose=args.verbose,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
