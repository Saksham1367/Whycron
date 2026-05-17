"""One-shot Sentry smoke test.

Fires a single ``capture_message`` and a single captured exception to the
configured DSN, flushes, and exits. Used to confirm the wire from app
config to the Sentry project actually works without spinning up uvicorn.

Run with:

    uv run python scripts/sentry_smoke.py

Then check the Sentry dashboard for the two events (one info-level
message and one ZeroDivisionError) tagged ``phase=10c-smoke``.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sentry_sdk  # noqa: E402

from apps.api.config import settings  # noqa: E402


def main() -> int:
    if not settings.sentry_dsn:
        print("SENTRY_DSN is not set in .env — nothing to test.", file=sys.stderr)
        return 1

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("phase", "10c-smoke")
    sentry_sdk.set_tag("source", "sentry_smoke.py")

    sentry_sdk.capture_message(
        "Whycron Phase 10c smoke: hello from sentry_smoke.py",
        level="info",
    )
    print("Captured info message.")

    try:
        _ = 1 / 0
    except ZeroDivisionError:
        sentry_sdk.capture_exception()
        print("Captured ZeroDivisionError.")

    flushed = sentry_sdk.flush(timeout=10.0)
    print(f"Sentry flushed: {flushed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
