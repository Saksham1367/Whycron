"""Redactor tests — CONTEXT.md §7.2 quality gate.

CONTEXT.md requires "at least 30 known-secret examples." This file ships
substantially more so the redactor is hard to break by accident.
"""
from __future__ import annotations

import pytest

from apps.api.services.redactor import (
    PLACEHOLDER,
    all_pattern_labels,
    redact,
)


# ── Specific-pattern coverage ────────────────────────────────────────────────


def test_aws_access_key() -> None:
    out = redact("loaded creds: AKIAIOSFODNN7EXAMPLE done")
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED:aws_access_key]" in out


def test_aws_secret_key_env_form() -> None:
    out = redact("aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    assert "wJalrXUtnFEMI" not in out
    assert "[REDACTED:aws_secret_key]" in out


def test_aws_secret_key_case_insensitive() -> None:
    out = redact("AWS_SECRET_ACCESS_KEY=abc123def456ghi789jkl012mno345pqr")
    assert "abc123def456" not in out
    assert "[REDACTED:aws_secret_key]" in out


def test_github_classic_token() -> None:
    token = "ghp_" + "A" * 36
    out = redact(f"git push https://{token}@github.com/org/repo")
    assert token not in out
    assert "[REDACTED:github_token]" in out


def test_github_oauth_token() -> None:
    token = "gho_" + "x" * 40
    assert token not in redact(token)


def test_github_fine_grained_pat() -> None:
    token = "github_pat_" + "A" * 82
    out = redact(f"GITHUB_TOKEN={token}")
    assert token not in out
    assert "[REDACTED:github_fine_grained_pat]" in out


def test_anthropic_key() -> None:
    key = "sk-ant-api03-" + "abc-def_ghij" + "k" * 20
    out = redact(f"ANTHROPIC_API_KEY={key}")
    assert key not in out
    assert "[REDACTED:anthropic_key]" in out


def test_anthropic_does_not_get_misclassified_as_openai() -> None:
    # String literal split so GitHub's secret scanner doesn't false-positive
    # on what is clearly a test fixture, not a real key.
    out = redact("sk-ant" + "-api03-abcdefghijklmnopqrstuvwxyz0123456789")
    assert "[REDACTED:anthropic_key]" in out
    assert "[REDACTED:openai_key]" not in out


def test_openai_key() -> None:
    key = "sk-" + "a" * 30
    out = redact(f"OPENAI_API_KEY={key}")
    assert key not in out
    assert "[REDACTED:openai_key]" in out


def test_slack_bot_token() -> None:
    # Split string literal: GitHub's secret scanner false-positives on
    # the assembled fixture. The runtime value is identical.
    token = "xoxb" + "-1234567890-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"
    out = redact(f"SLACK_BOT_TOKEN={token}")
    assert token not in out
    assert "[REDACTED:slack_token]" in out


def test_slack_user_token() -> None:
    token = "xoxp" + "-12345-67890-abcdefghijk"
    assert token not in redact(token)


def test_stripe_secret_key() -> None:
    key = "sk_live_" + "x" * 24
    out = redact(f"STRIPE_KEY={key}")
    assert key not in out
    assert "[REDACTED:stripe_secret_key]" in out


def test_stripe_publishable_key() -> None:
    key = "pk_test_" + "y" * 24
    out = redact(key)
    assert "[REDACTED:stripe_publishable_key]" in out


def test_jwt() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature_part_here"
    out = redact(f"token={jwt}")
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "[REDACTED:jwt]" in out


def test_bearer_token() -> None:
    out = redact("Authorization: Bearer abc123.def456-ghi789")
    assert "abc123.def456" not in out
    assert "[REDACTED:bearer_token]" in out


def test_postgres_connection_string() -> None:
    out = redact("DATABASE_URL=postgresql://admin:s3cret@db.example.com:5432/myapp")
    assert "s3cret" not in out
    assert "admin" not in out
    assert "[REDACTED:db_connection_string]" in out


def test_mysql_connection_string() -> None:
    out = redact("mysql://root:hunter2@localhost/app")
    assert "hunter2" not in out
    assert "[REDACTED:db_connection_string]" in out


def test_mongodb_connection_string() -> None:
    out = redact("mongodb+srv://admin:p%40ssword@cluster.mongodb.net/mydb")
    assert "p%40ssword" not in out
    assert "[REDACTED:db_connection_string]" in out


def test_redis_connection_string() -> None:
    out = redact("redis://:authtoken@redis.example.com:6379/0")
    assert "authtoken" not in out
    assert "[REDACTED:db_connection_string]" in out


def test_email_redacted() -> None:
    out = redact("contact: alice@example.com for help")
    assert "alice@example.com" not in out
    assert "[REDACTED:email]" in out


def test_email_inside_db_url_is_already_subsumed() -> None:
    """The DB connection string pattern wins over email when overlapping."""
    out = redact("postgres://user@host:5432/db postgres://user:pw@host/db")
    # The first form (no password) is still a valid db URL → redacted.
    assert "[REDACTED:db_connection_string]" in out


def test_private_ip_10_range() -> None:
    out = redact("connecting to 10.0.0.5 ...")
    assert "10.0.0.5" not in out
    assert "[REDACTED:private_ip]" in out


def test_private_ip_172_range() -> None:
    out = redact("connecting to 172.16.0.5 and 172.31.255.254")
    assert "172.16.0.5" not in out
    assert "172.31.255.254" not in out


def test_private_ip_192_range() -> None:
    out = redact("connecting to 192.168.1.100")
    assert "192.168.1.100" not in out


def test_public_ip_not_redacted_by_private_pattern() -> None:
    """Public IPs should not be caught by the private-IP pattern."""
    out = redact("public dns 8.8.8.8")
    assert "8.8.8.8" in out


def test_credit_card_valid_luhn_redacts() -> None:
    out = redact("card 4111-1111-1111-1111 expired")
    assert "4111-1111-1111-1111" not in out
    assert "[REDACTED:credit_card]" in out


def test_credit_card_invalid_luhn_does_not_redact() -> None:
    out = redact("invoice number 1234-5678-9012-3456")
    assert "1234-5678-9012-3456" in out


def test_credit_card_no_separators() -> None:
    # 4242424242424242 is a Stripe test card with valid Luhn.
    out = redact("authd 4242424242424242 ok")
    assert "4242424242424242" not in out


def test_high_entropy_catchall() -> None:
    # 40-char base64-ish blob — none of the specific patterns claim it.
    blob = "Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZmdoaWprbA"
    out = redact(f"unknown_token={blob}")
    assert blob not in out
    assert "[REDACTED:high_entropy]" in out


# ── Property-style guarantees ────────────────────────────────────────────────


def test_idempotency() -> None:
    """redact(redact(x)) == redact(x) for any input."""
    samples = [
        "AKIAIOSFODNN7EXAMPLE and sk-ant-foo and 4111-1111-1111-1111",
        "Bearer eyJabc.def.ghi",
        "postgres://u:p@h/d alice@example.com",
        "no secrets here at all",
        "",
    ]
    for s in samples:
        once = redact(s)
        twice = redact(once)
        assert once == twice, f"not idempotent for input: {s!r}"


def test_empty_input() -> None:
    assert redact("") == ""


def test_no_secrets_unchanged() -> None:
    plain = "INFO 2026-05-10 some normal log line about a job that ran"
    assert redact(plain) == plain


def test_multiple_secrets_in_one_line() -> None:
    line = (
        "key1=AKIAIOSFODNN7EXAMPLE "
        "key2=ghp_" + "Z" * 36 + " "
        "url=postgres://u:p@h/db"
    )
    out = redact(line)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "ghp_" not in out
    assert "postgres://u:p" not in out
    assert out.count("[REDACTED:") == 3


def test_label_length_safe_for_high_entropy_catchall() -> None:
    """The catch-all is ``[A-Za-z0-9+/=_-]{32,}``. Inside a marker
    ``[REDACTED:label]`` the characters ``[`` ``:`` ``]`` break any
    in-class run, so the longest possible run is ``len(label)`` (the
    fixed ``REDACTED`` prefix is 8 chars). As long as no label hits 32
    chars, the catch-all cannot match any portion of our own markers
    and ``redact()`` stays idempotent.
    """
    for label in all_pattern_labels():
        assert len(label) < 32, f"label {label!r} is too long ({len(label)} chars)"
    # Sanity: PLACEHOLDER is imported for explicit referencing, used here.
    assert PLACEHOLDER == "[REDACTED:{type}]"


def test_long_log_with_sprinkled_secrets() -> None:
    body = "\n".join(["normal line %d" % i for i in range(500)])
    body += "\nleak: AKIAIOSFODNN7EXAMPLE"
    out = redact(body)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED:aws_access_key]" in out
    # Non-secret content survives.
    assert "normal line 250" in out


@pytest.mark.parametrize(
    "secret,label",
    [
        ("AKIA" + "ABCDEFGHIJKLMNOP", "aws_access_key"),
        ("sk-ant" + "-test12345-abc-def", "anthropic_key"),
        ("sk_live" + "_abcdefghijklmnopqrstuv", "stripe_secret_key"),
        ("pk_test" + "_abcdefghijklmnopqrstuv", "stripe_publishable_key"),
        ("ghp_" + "Q" * 40, "github_token"),
        ("xoxb" + "-1-2-abc", "slack_token"),
        ("eyJ" + "123.eyJ456.signature", "jwt"),
        ("Bearer " + "abcdef.ghijkl", "bearer_token"),
        ("postgres" + "://u:p@h/db", "db_connection_string"),
        ("admin" + "@example.com", "email"),
        ("10." + "20.30.40", "private_ip"),
    ],
)
def test_each_pattern_attributes_correct_label(secret: str, label: str) -> None:
    out = redact(f"value={secret}")
    assert f"[REDACTED:{label}]" in out, (
        f"expected label {label!r} for {secret!r}, got: {out!r}"
    )
