"""Unit tests for the Whycron Python SDK.

These tests run against a mocked HTTP layer (pytest-httpx) — no network,
no Whycron instance required.
"""
from __future__ import annotations

import json

import pytest

from whycron import (
    Whycron,
    WhycronAPIError,
    WhycronAuthError,
    WhycronNotFoundError,
    WhycronRateLimitedError,
    monitor,
)

BASE = "https://api.whycron.com"
TOKEN = "wcr_abc123def456"
API_KEY = "wcr_live_testtesttest"


# ── ping ─────────────────────────────────────────────────────────────────────


def test_ping_succeeded_hits_bare_path(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/p/{TOKEN}",
        json={"status": "ok", "run_id": "abc"},
    )
    with Whycron() as client:
        result = client.ping(TOKEN)
    assert result == {"status": "ok", "run_id": "abc"}


def test_ping_failed_appends_state_to_path(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/p/{TOKEN}/failed",
        json={"status": "ok", "run_id": "xyz"},
    )
    with Whycron() as client:
        result = client.ping(
            TOKEN, state="failed", exit_code=1, duration_ms=1234, logs="boom"
        )
    assert result["run_id"] == "xyz"
    sent = httpx_mock.get_requests()[0]
    body = json.loads(sent.content)
    assert body == {"exit_code": 1, "duration_ms": 1234, "logs": "boom"}


def test_ping_started_uses_started_path(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/p/{TOKEN}/started",
        json={"status": "ok", "run_id": "r1"},
    )
    with Whycron() as client:
        client.ping(TOKEN, state="started")


def test_ping_with_external_id_includes_state_segment(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/p/{TOKEN}/succeeded/job-42",
        json={"status": "ok", "run_id": "r1"},
    )
    with Whycron() as client:
        client.ping(TOKEN, state="succeeded", external_id="job-42")


def test_ping_with_metadata_serializes_to_json(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/p/{TOKEN}",
        json={"status": "ok", "run_id": "r1"},
    )
    with Whycron() as client:
        client.ping(TOKEN, metadata={"env": "prod", "host": "worker-1"})
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body == {"metadata": {"env": "prod", "host": "worker-1"}}


# ── monitor CRUD ─────────────────────────────────────────────────────────────


def test_create_monitor_sends_api_key_header(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/api/v1/monitors",
        json={"id": "m1", "name": "Backup"},
        status_code=201,
    )
    with Whycron(api_key=API_KEY) as client:
        result = client.create_monitor(
            name="Backup", schedule_type="cron", schedule_value="0 2 * * *"
        )
    assert result["id"] == "m1"
    req = httpx_mock.get_requests()[0]
    assert req.headers["x-whycron-api-key"] == API_KEY
    body = json.loads(req.content)
    assert body["name"] == "Backup"
    assert body["schedule_type"] == "cron"
    assert body["schedule_value"] == "0 2 * * *"


def test_list_monitors_with_filters(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE}/api/v1/monitors?limit=10&offset=0&status=failing",
        json={"items": []},
    )
    with Whycron(api_key=API_KEY) as client:
        client.list_monitors(status="failing", limit=10)


def test_get_monitor(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE}/api/v1/monitors/m1",
        json={"id": "m1", "name": "Backup"},
    )
    with Whycron(api_key=API_KEY) as client:
        result = client.get_monitor("m1")
    assert result["name"] == "Backup"


def test_update_monitor_requires_at_least_one_field() -> None:
    with Whycron(api_key=API_KEY) as client, pytest.raises(ValueError):
        client.update_monitor("m1")


def test_update_monitor_sends_patch_body(httpx_mock) -> None:
    httpx_mock.add_response(
        method="PATCH",
        url=f"{BASE}/api/v1/monitors/m1",
        json={"id": "m1", "name": "Renamed"},
    )
    with Whycron(api_key=API_KEY) as client:
        client.update_monitor("m1", name="Renamed", paused=True)
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body == {"name": "Renamed", "paused": True}


def test_delete_monitor_swallows_204(httpx_mock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE}/api/v1/monitors/m1",
        status_code=204,
    )
    with Whycron(api_key=API_KEY) as client:
        client.delete_monitor("m1")


# ── runs ─────────────────────────────────────────────────────────────────────


def test_list_runs_with_monitor_filter(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE}/api/v1/runs?limit=50&offset=0&monitor_id=m1",
        json={"items": []},
    )
    with Whycron(api_key=API_KEY) as client:
        client.list_runs(monitor_id="m1")


def test_get_run(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE}/api/v1/runs/r1",
        json={"id": "r1", "state": "succeeded"},
    )
    with Whycron(api_key=API_KEY) as client:
        result = client.get_run("r1")
    assert result["state"] == "succeeded"


# ── auth/error handling ─────────────────────────────────────────────────────


def test_missing_api_key_raises_before_request() -> None:
    with Whycron() as client, pytest.raises(WhycronAPIError) as exc_info:
        client.list_monitors()
    assert "api_key is required" in str(exc_info.value)


def test_401_raises_auth_error(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE}/api/v1/monitors?limit=50&offset=0",
        status_code=401,
        json={"detail": "Invalid or revoked API key"},
    )
    with Whycron(api_key=API_KEY) as client, pytest.raises(WhycronAuthError) as exc:
        client.list_monitors()
    assert exc.value.status_code == 401


def test_404_raises_not_found(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE}/api/v1/monitors/nope",
        status_code=404,
        json={"detail": "Monitor not found"},
    )
    with Whycron(api_key=API_KEY) as client, pytest.raises(WhycronNotFoundError):
        client.get_monitor("nope")


def test_429_raises_rate_limited(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/p/{TOKEN}",
        status_code=429,
        json={"detail": "Rate limited"},
    )
    with Whycron() as client, pytest.raises(WhycronRateLimitedError):
        client.ping(TOKEN)


# ── decorator ───────────────────────────────────────────────────────────────


def test_monitor_decorator_pings_started_and_succeeded(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE}/p/{TOKEN}/started", json={"status": "ok"}
    )
    httpx_mock.add_response(
        method="POST", url=f"{BASE}/p/{TOKEN}", json={"status": "ok"}
    )
    client = Whycron()

    @monitor(TOKEN, client=client)
    def work() -> int:
        return 42

    result = work()
    assert result == 42

    reqs = httpx_mock.get_requests()
    assert reqs[0].url.path.endswith("/started")
    assert reqs[1].url.path == f"/p/{TOKEN}"
    succeeded_body = json.loads(reqs[1].content)
    assert succeeded_body["exit_code"] == 0
    assert isinstance(succeeded_body["duration_ms"], int)


def test_monitor_decorator_pings_failed_on_exception_and_reraises(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{BASE}/p/{TOKEN}/started", json={"status": "ok"}
    )
    httpx_mock.add_response(
        method="POST", url=f"{BASE}/p/{TOKEN}/failed", json={"status": "ok"}
    )
    client = Whycron()

    @monitor(TOKEN, client=client)
    def broken() -> None:
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        broken()

    reqs = httpx_mock.get_requests()
    failed_body = json.loads(reqs[1].content)
    assert failed_body["exit_code"] == 1
    assert "ValueError: kaboom" in failed_body["logs"]


def test_decorator_does_not_swallow_ping_failures_into_callee(httpx_mock) -> None:
    # First ping (started) fails — the wrapped function must still run.
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE}/p/{TOKEN}/started",
        status_code=500,
        json={"detail": "boom"},
    )
    httpx_mock.add_response(
        method="POST", url=f"{BASE}/p/{TOKEN}", json={"status": "ok"}
    )
    client = Whycron()

    @monitor(TOKEN, client=client)
    def work() -> str:
        return "ran-anyway"

    assert work() == "ran-anyway"
