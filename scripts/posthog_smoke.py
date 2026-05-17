"""One-shot PostHog smoke test.

Fires a single ``monitor_created_smoke`` event to the configured PostHog
project, flushes, and exits. Used to confirm the wire from app config
to the PostHog project actually works without spinning up uvicorn.

Run with:

    uv run python scripts/posthog_smoke.py

Then check the PostHog "Activity" / Live Events for an event named
``monitor_created_smoke`` from distinct_id ``phase-10c-smoke-user``.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from posthog import Posthog  # noqa: E402

from apps.api.config import settings  # noqa: E402


def main() -> int:
    if not settings.posthog_api_key:
        print(
            "POSTHOG_API_KEY is not set in .env — nothing to test.",
            file=sys.stderr,
        )
        return 1

    client = Posthog(
        project_api_key=settings.posthog_api_key,
        host=settings.posthog_host,
        disable_geoip=True,
        sync_mode=False,
    )

    client.capture(
        distinct_id="phase-10c-smoke-user",
        event="monitor_created_smoke",
        properties={
            "source": "posthog_smoke.py",
            "phase": "10c-smoke",
            "ts": int(time.time()),
        },
    )
    print("Captured monitor_created_smoke event.")

    client.shutdown()
    print("PostHog client shut down (events flushed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
