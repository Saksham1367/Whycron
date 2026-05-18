"""``@whycron.monitor`` — wrap a function so every call pings Whycron.

Sends a ``started`` ping before the function runs, then a ``succeeded``
or ``failed`` ping after based on whether the function returned normally
or raised. Captures the traceback as the ``logs`` payload on failure and
records the wall-clock duration in milliseconds.

The decorator never swallows the underlying exception — failures still
propagate to the caller after the ping is sent.

Example::

    import whycron

    @whycron.monitor("wcr_abc123def")
    def nightly_backup():
        ...

    # Or with a custom client (different base URL, injected for testing):
    custom = whycron.Whycron(base_url="https://api.staging.example.com")

    @whycron.monitor("wcr_abc123def", client=custom)
    def staging_job():
        ...
"""
from __future__ import annotations

import functools
import logging
import time
import traceback
from typing import Any, Callable, TypeVar, cast

from whycron.client import Whycron

F = TypeVar("F", bound=Callable[..., Any])

_log = logging.getLogger("whycron")
_default_client: Whycron | None = None


def _get_default_client() -> Whycron:
    global _default_client
    if _default_client is None:
        # No API key — ping doesn't need one, the ping_token is the credential.
        _default_client = Whycron(api_key=None)
    return _default_client


def monitor(
    ping_token: str,
    *,
    client: Whycron | None = None,
    capture_logs: bool = True,
    log_tail_chars: int = 4000,
) -> Callable[[F], F]:
    """Decorate a function so every call records start/success/failure with Whycron.

    :param ping_token: From your monitor row, starts with ``wcr_``.
    :param client: Override the default :class:`Whycron` instance. Useful for
        tests or for talking to a non-default base URL.
    :param capture_logs: If True (default), the traceback is sent as the
        ``logs`` payload on failure. Set False if you'd rather not transmit
        traceback content.
    :param log_tail_chars: Tail the traceback to this many chars before
        sending. Whycron will redact secrets server-side but smaller
        payloads also cost less to process.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            wc = client or _get_default_client()
            _safe_ping(wc, ping_token, state="started")
            started = time.monotonic()
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                logs: str | None = None
                if capture_logs:
                    tb = "".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    )
                    logs = tb[-log_tail_chars:]
                _safe_ping(
                    wc,
                    ping_token,
                    state="failed",
                    exit_code=1,
                    duration_ms=duration_ms,
                    logs=logs,
                )
                raise
            else:
                duration_ms = int((time.monotonic() - started) * 1000)
                _safe_ping(
                    wc,
                    ping_token,
                    state="succeeded",
                    exit_code=0,
                    duration_ms=duration_ms,
                )
                return result

        return cast(F, wrapper)

    return decorator


def _safe_ping(client: Whycron, token: str, **kwargs: Any) -> None:
    """Pinging must never break the wrapped function. Log and continue."""
    try:
        client.ping(token, **kwargs)
    except Exception as exc:  # noqa: BLE001
        _log.warning("whycron ping failed: %s", exc)
