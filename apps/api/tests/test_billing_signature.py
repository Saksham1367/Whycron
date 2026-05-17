"""Standard Webhooks v1 signature verification tests (CONTEXT.md §7.4)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest

from apps.api.services.billing import (
    WebhookSignatureError,
    verify_polar_signature,
)

# A long base64-clean test secret.
TEST_SECRET_RAW = b"test-secret-bytes-that-are-long-enough-for-hmac-sha256"
TEST_SECRET = base64.b64encode(TEST_SECRET_RAW).decode()


def _sign(
    body: bytes,
    *,
    secret_bytes: bytes = TEST_SECRET_RAW,
    webhook_id: str = "evt_test_001",
    timestamp: int | None = None,
) -> dict[str, str]:
    ts = timestamp if timestamp is not None else int(time.time())
    signing_string = f"{webhook_id}.{ts}.".encode() + body
    digest = hmac.new(secret_bytes, signing_string, hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode()
    return {
        "webhook-id": webhook_id,
        "webhook-timestamp": str(ts),
        "webhook-signature": f"v1,{sig}",
    }


def test_accepts_well_formed_signature() -> None:
    body = b'{"type":"subscription.created","data":{}}'
    headers = _sign(body)
    event_id = verify_polar_signature(
        secret=TEST_SECRET, headers=headers, body=body
    )
    assert event_id == "evt_test_001"


def test_rejects_tampered_body() -> None:
    body = b'{"type":"subscription.created","data":{}}'
    headers = _sign(body)
    with pytest.raises(WebhookSignatureError):
        verify_polar_signature(
            secret=TEST_SECRET,
            headers=headers,
            body=body + b" tampered",
        )


def test_rejects_wrong_secret() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    other_secret = base64.b64encode(b"a-different-secret-entirely-here").decode()
    with pytest.raises(WebhookSignatureError):
        verify_polar_signature(
            secret=other_secret, headers=headers, body=body
        )


def test_rejects_stale_timestamp() -> None:
    body = b'{"type":"x"}'
    # 10 minutes in the past — outside the 5-min tolerance.
    headers = _sign(body, timestamp=int(time.time()) - 600)
    with pytest.raises(WebhookSignatureError, match="tolerance"):
        verify_polar_signature(
            secret=TEST_SECRET, headers=headers, body=body
        )


def test_rejects_future_timestamp() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body, timestamp=int(time.time()) + 600)
    with pytest.raises(WebhookSignatureError, match="tolerance"):
        verify_polar_signature(
            secret=TEST_SECRET, headers=headers, body=body
        )


def test_rejects_missing_id_header() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    del headers["webhook-id"]
    with pytest.raises(WebhookSignatureError, match="missing"):
        verify_polar_signature(
            secret=TEST_SECRET, headers=headers, body=body
        )


def test_rejects_missing_signature_header() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    del headers["webhook-signature"]
    with pytest.raises(WebhookSignatureError, match="missing"):
        verify_polar_signature(
            secret=TEST_SECRET, headers=headers, body=body
        )


def test_rejects_non_integer_timestamp() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    headers["webhook-timestamp"] = "not-a-number"
    with pytest.raises(WebhookSignatureError, match="integer"):
        verify_polar_signature(
            secret=TEST_SECRET, headers=headers, body=body
        )


def test_rejects_v2_only_signature() -> None:
    """An unknown algorithm version must NOT be accepted as v1."""
    body = b'{"type":"x"}'
    headers = _sign(body)
    # Strip the v1 prefix and pretend it's v2.
    sig = headers["webhook-signature"].split(",", 1)[1]
    headers["webhook-signature"] = f"v2,{sig}"
    with pytest.raises(WebhookSignatureError):
        verify_polar_signature(
            secret=TEST_SECRET, headers=headers, body=body
        )


def test_accepts_signature_with_whsec_prefix() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    prefixed_secret = "whsec_" + TEST_SECRET
    event_id = verify_polar_signature(
        secret=prefixed_secret, headers=headers, body=body
    )
    assert event_id == "evt_test_001"


def test_accepts_signature_with_polar_whsec_prefix() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    prefixed_secret = "polar_whsec_" + TEST_SECRET
    event_id = verify_polar_signature(
        secret=prefixed_secret, headers=headers, body=body
    )
    assert event_id == "evt_test_001"


def test_accepts_when_multiple_signatures_offered() -> None:
    """Standard Webhooks supports key rotation by sending multiple sigs.
    Receivers must accept the delivery as long as one valid signature
    is present."""
    body = b'{"type":"x"}'
    headers = _sign(body)
    valid = headers["webhook-signature"]
    headers["webhook-signature"] = f"v1,definitely-not-valid {valid}"
    event_id = verify_polar_signature(
        secret=TEST_SECRET, headers=headers, body=body
    )
    assert event_id == "evt_test_001"


def test_rejects_empty_secret() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    with pytest.raises(WebhookSignatureError, match="not configured"):
        verify_polar_signature(secret="", headers=headers, body=body)


def test_header_lookup_is_case_insensitive() -> None:
    body = b'{"type":"x"}'
    headers = _sign(body)
    upper = {k.upper(): v for k, v in headers.items()}
    event_id = verify_polar_signature(
        secret=TEST_SECRET, headers=upper, body=body
    )
    assert event_id == "evt_test_001"
