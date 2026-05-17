"""Failure signature hash tests."""
from __future__ import annotations

from apps.api.services.signature import signature_hash


def test_format_is_sha256_prefixed() -> None:
    h = signature_hash(1, "anything")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_identical_inputs_produce_identical_hash() -> None:
    a = signature_hash(1, "ERROR: disk full\nfailed to write archive")
    b = signature_hash(1, "ERROR: disk full\nfailed to write archive")
    assert a == b


def test_different_exit_codes_diverge() -> None:
    a = signature_hash(1, "ERROR: disk full")
    b = signature_hash(137, "ERROR: disk full")
    assert a != b


def test_different_messages_diverge() -> None:
    a = signature_hash(1, "ERROR: disk full")
    b = signature_hash(1, "ERROR: connection refused")
    assert a != b


def test_timestamps_normalized_away() -> None:
    a = signature_hash(1, "2026-05-10T18:00:00Z ERROR connection refused")
    b = signature_hash(1, "2026-05-11T03:14:22Z ERROR connection refused")
    assert a == b


def test_uuids_normalized_away() -> None:
    a = signature_hash(
        1, "request abc12345-6789-4abc-9def-012345678901 failed: timeout"
    )
    b = signature_hash(
        1, "request fedcba98-7654-4321-8abc-0123456789ab failed: timeout"
    )
    assert a == b


def test_hex_hashes_normalized_away() -> None:
    a = signature_hash(1, "commit 1234567890abcdef1234567890abcdef build failed")
    b = signature_hash(1, "commit fedcba0987654321fedcba0987654321 build failed")
    assert a == b


def test_pids_and_line_numbers_normalized_away() -> None:
    a = signature_hash(1, "pid=12345 at line 678 in module")
    b = signature_hash(1, "pid=99999 at line 4242 in module")
    assert a == b


def test_lines_beyond_the_last_ten_dont_influence_hash() -> None:
    """The hash is computed from the last 10 lines only — adding prefix
    history must not change the result."""
    last_10 = "\n".join(f"err line {i}" for i in range(10))
    extra_history = "\n".join(f"header line {i}" for i in range(40))
    a = signature_hash(1, f"{extra_history}\n{last_10}")
    b = signature_hash(1, last_10)
    assert a == b


def test_empty_log_is_stable() -> None:
    a = signature_hash(1, "")
    b = signature_hash(1, None)
    assert a == b


def test_none_exit_code_distinct_from_zero() -> None:
    a = signature_hash(None, "x")
    b = signature_hash(0, "x")
    assert a != b
