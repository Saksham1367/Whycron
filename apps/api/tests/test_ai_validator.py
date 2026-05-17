"""Hallucination-validator unit tests."""
from __future__ import annotations

from apps.api.services.ai_validator import extract_citations, grade_confidence


def test_extract_pulls_backticks() -> None:
    out = extract_citations("Use `pg_dump` and check `disk space`.")
    assert "pg_dump" in out
    assert "disk space" in out


def test_extract_pulls_all_caps_identifiers() -> None:
    out = extract_citations("Got ERROR and FATAL: OOMKilled")
    assert "ERROR" in out
    assert "FATAL" in out
    # 'OOMKilled' has lowercase letters, so it's NOT pure all-caps.
    assert "OOMKilled" not in out


def test_extract_pulls_paths() -> None:
    out = extract_citations(
        "Failed writing /var/backups/db.sql and C:\\Logs\\app.log"
    )
    assert "/var/backups/db.sql" in out
    assert "C:\\Logs\\app.log" in out


def test_extract_deduplicates() -> None:
    out = extract_citations("`pg_dump` failed, `pg_dump` retried, FATAL FATAL")
    assert out.count("pg_dump") == 1
    assert out.count("FATAL") == 1


def test_high_confidence_when_all_grounded() -> None:
    explanation = (
        "Job failed because `pg_dump` returned an ENOSPC error.\n"
        "The backup volume hit FATAL capacity limits.\n"
        "Free space on the backup mount."
    )
    logs = (
        "ERROR pg_dump: write to file failed: ENOSPC: No space left on device\n"
        "FATAL: backup volume is full"
    )
    assert grade_confidence(explanation, logs) == "high"


def test_low_confidence_when_hallucinating() -> None:
    explanation = (
        "Job failed because `mysqldump` hit `EACCES` on /var/cache.\n"
        "The PERMISSION_DENIED chain prevented the dump.\n"
        "Check FILESYSTEM ACLs."
    )
    logs = "totally unrelated stuff: connection timed out at 09:00 UTC"
    assert grade_confidence(explanation, logs) == "low"


def test_medium_when_no_specific_citations() -> None:
    # No backticks, no caps, no paths — nothing to verify.
    explanation = (
        "Job failed because the database was unreachable.\n"
        "Connection was refused after several retries.\n"
        "Check the database is running and reachable."
    )
    logs = "anything goes here"
    assert grade_confidence(explanation, logs) == "medium"


def test_medium_when_most_grounded_but_not_all() -> None:
    # 3 citations, 2 grounded → ratio 0.67 → below 0.7 threshold → low.
    # Adjust to hit medium: 4 citations, 3 grounded → 0.75 → medium.
    explanation = (
        "Saw ERROR FATAL `pg_dump` and TIMEOUT.\n"
        "Standard chain.\n"
        "Investigate."
    )
    logs = "got ERROR FATAL during pg_dump run"  # TIMEOUT missing
    assert grade_confidence(explanation, logs) == "medium"
