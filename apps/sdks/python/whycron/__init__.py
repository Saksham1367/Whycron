"""Whycron — Python client for the cron monitoring service.

Quick start::

    from whycron import Whycron

    client = Whycron(api_key="wcr_live_...")

    # Heartbeat pings — no API key required; the ping token IS the credential.
    client.ping("wcr_abc123def", state="started")
    try:
        do_the_work()
        client.ping("wcr_abc123def", state="succeeded")
    except Exception as exc:
        client.ping("wcr_abc123def", state="failed", logs=str(exc), exit_code=1)
        raise

Or use the decorator::

    import whycron

    @whycron.monitor("wcr_abc123def")
    def nightly_backup():
        ...
"""
from whycron.client import Whycron
from whycron.decorator import monitor
from whycron.exceptions import (
    WhycronAPIError,
    WhycronAuthError,
    WhycronError,
    WhycronNotFoundError,
    WhycronRateLimitedError,
)

__version__ = "0.1.0"
__all__ = [
    "Whycron",
    "WhycronAPIError",
    "WhycronAuthError",
    "WhycronError",
    "WhycronNotFoundError",
    "WhycronRateLimitedError",
    "monitor",
    "__version__",
]
