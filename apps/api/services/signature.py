"""Failure signature hash (CONTEXT.md §4.2.5).

Computed as ``sha256(exit_code | normalized_last_10_log_lines)``. Two runs
that fail the same way produce the same hash, enabling explanation dedup
in V1 (§8.3) and the V3 failure-pattern library.

"Normalized" here means: strip the parts of a log line that change run-to-
run for an *identical* failure — timestamps, UUIDs, hex hashes, large
numbers (PIDs, line numbers, byte counts). The resulting hash is stable
across reruns, hosts, and time.
"""
from __future__ import annotations

import hashlib
import re

_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?"
)
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX_HASH_RE = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_LARGE_INT_RE = re.compile(r"\b\d{3,}\b")

_LAST_N_LINES = 10


def _normalize_line(line: str) -> str:
    line = _TIMESTAMP_RE.sub("<TS>", line)
    line = _UUID_RE.sub("<UUID>", line)
    line = _HEX_HASH_RE.sub("<HASH>", line)
    line = _LARGE_INT_RE.sub("<N>", line)
    return line.strip()


def signature_hash(exit_code: int | None, log_excerpt: str | None) -> str:
    """Return the deterministic failure signature for a run.

    ``log_excerpt`` is the redacted excerpt as it will be stored — passing
    pre-redaction logs in here would let secrets influence the hash, which
    is undesirable.
    """
    lines = (log_excerpt or "").splitlines()[-_LAST_N_LINES:]
    normalized = "\n".join(_normalize_line(line) for line in lines)
    payload = f"exit_code={exit_code}|{normalized}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
