"""Webhook HMAC signing + retry tests."""
from __future__ import annotations

import hashlib
import hmac

import pytest

from apps.api.services.notify.webhook import (
    WebhookDeliveryFailed,
    send_signed_webhook,
    sign_payload,
)


# ── HMAC signing ─────────────────────────────────────────────────────────────


def test_sign_payload_produces_expected_headers() -> None:
    headers = sign_payload("topsecret", b'{"hello":"world"}', timestamp=1700000000)
    assert headers["X-Whycron-Timestamp"] == "1700000000"
    assert headers["X-Whycron-Signature"].startswith("v1=")


def test_sign_payload_is_deterministic_for_same_inputs() -> None:
    a = sign_payload("k", b"body", timestamp=42)
    b = sign_payload("k", b"body", timestamp=42)
    assert a == b


def test_sign_payload_changes_with_timestamp() -> None:
    a = sign_payload("k", b"body", timestamp=1)
    b = sign_payload("k", b"body", timestamp=2)
    assert a["X-Whycron-Signature"] != b["X-Whycron-Signature"]


def test_sign_payload_changes_with_body() -> None:
    a = sign_payload("k", b"body1", timestamp=1)
    b = sign_payload("k", b"body2", timestamp=1)
    assert a["X-Whycron-Signature"] != b["X-Whycron-Signature"]


def test_sign_payload_verifies_via_independent_hmac() -> None:
    """A receiver re-computing the HMAC must get the same digest."""
    secret = "shh"
    body = b'{"event":"test"}'
    timestamp = 1700000000
    headers = sign_payload(secret, body, timestamp=timestamp)
    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-Whycron-Signature"] == f"v1={expected}"


# ── Send + retry behavior ────────────────────────────────────────────────────


pytestmark_offline = pytest.mark.asyncio


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = ""


class _FakeAsyncClient:
    """Stand-in for ``httpx.AsyncClient`` that returns a scripted sequence
    of status codes (or raises ``httpx.RequestError``)."""

    def __init__(self, responses: list[int | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url, *, content, headers, follow_redirects):
        self.calls.append(
            {
                "url": url,
                "content": content,
                "headers": dict(headers),
                "follow_redirects": follow_redirects,
            }
        )
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _FakeResponse(nxt)


@pytest.fixture
def public_ssrf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass SSRF validation — we're not testing DNS here."""
    monkeypatch.setattr(
        "apps.api.services.notify.webhook.validate_webhook_url",
        lambda url: None,
    )


async def test_send_signed_webhook_succeeds(
    public_ssrf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeAsyncClient([200])
    monkeypatch.setattr(
        "apps.api.services.notify.webhook.httpx.AsyncClient",
        lambda timeout: fake,
    )

    status = await send_signed_webhook(
        "https://api.example.com/hook",
        {"event": "x"},
        secret="topsecret",
        delays_seconds=[],
    )
    assert status == 200
    assert len(fake.calls) == 1
    assert "X-Whycron-Signature" in fake.calls[0]["headers"]
    assert fake.calls[0]["follow_redirects"] is False


async def test_send_signed_webhook_retries_on_5xx(
    public_ssrf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeAsyncClient([500, 502, 200])
    monkeypatch.setattr(
        "apps.api.services.notify.webhook.httpx.AsyncClient",
        lambda timeout: fake,
    )

    status = await send_signed_webhook(
        "https://api.example.com/hook",
        {"event": "x"},
        secret="topsecret",
        delays_seconds=[0, 0, 0, 0],
    )
    assert status == 200
    assert len(fake.calls) == 3


async def test_send_signed_webhook_does_not_retry_4xx(
    public_ssrf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeAsyncClient([400, 200])  # second response should never fire
    monkeypatch.setattr(
        "apps.api.services.notify.webhook.httpx.AsyncClient",
        lambda timeout: fake,
    )

    with pytest.raises(WebhookDeliveryFailed):
        await send_signed_webhook(
            "https://api.example.com/hook",
            {"event": "x"},
            secret="topsecret",
            delays_seconds=[0, 0, 0, 0],
        )
    assert len(fake.calls) == 1


async def test_send_signed_webhook_fails_after_max_attempts(
    public_ssrf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeAsyncClient([500, 502, 503, 504, 500])
    monkeypatch.setattr(
        "apps.api.services.notify.webhook.httpx.AsyncClient",
        lambda timeout: fake,
    )

    with pytest.raises(WebhookDeliveryFailed):
        await send_signed_webhook(
            "https://api.example.com/hook",
            {"event": "x"},
            secret="topsecret",
            delays_seconds=[0, 0, 0, 0],
        )
    # 5 attempts (initial + 4 retries) exhausted
    assert len(fake.calls) == 5


async def test_send_signed_webhook_rejects_unsigned() -> None:
    """No global signing secret, no per-channel secret → error before any
    network I/O."""
    with pytest.raises(WebhookDeliveryFailed):
        await send_signed_webhook(
            "https://api.example.com/hook",
            {"event": "x"},
            secret="",  # explicit empty
            delays_seconds=[],
        )
