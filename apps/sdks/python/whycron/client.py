"""Whycron HTTP client — thin httpx wrapper.

Two surfaces:

- :meth:`Whycron.ping` — heartbeat pings; the ping_token is the credential.
- All other methods — programmatic management; require an API key.
"""
from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping

import httpx

from whycron.exceptions import (
    WhycronAPIError,
    WhycronAuthError,
    WhycronNotFoundError,
    WhycronRateLimitedError,
)

DEFAULT_BASE_URL = "https://api.whycron.com"
DEFAULT_TIMEOUT = 10.0
USER_AGENT = "whycron-python/0.1.0"

PingState = Literal["succeeded", "failed", "started"]
ScheduleType = Literal["cron", "interval", "on_demand"]


class Whycron:
    """Synchronous client. For async, see :class:`AsyncWhycron`.

    :param api_key: A ``wcr_live_...`` key from Account → API keys.
        Required for monitor/run management. Optional if you only ping.
    :param base_url: Override the API host. Defaults to
        ``https://api.whycron.com``. Useful for self-hosted instances.
    :param timeout: Per-request timeout in seconds.
    :param transport: Inject an httpx transport (for tests, retries, etc.).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        )

    # ── lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Whycron":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── ping ─────────────────────────────────────────────────────────────────

    def ping(
        self,
        ping_token: str,
        *,
        state: PingState = "succeeded",
        exit_code: int | None = None,
        duration_ms: int | None = None,
        logs: str | None = None,
        external_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a heartbeat. No API key required — the ping token IS the credential.

        :param ping_token: From the monitor row, starts with ``wcr_``.
        :param state: ``succeeded`` (default), ``failed``, or ``started``.
        :param exit_code: Process exit code, if known.
        :param duration_ms: How long the job took, in milliseconds.
        :param logs: Log excerpt to attach. Pass the tail of stdout/stderr.
            Whycron's redactor strips secrets before storing or sending to
            the LLM, but please don't deliberately ship credentials.
        :param external_id: Idempotency key — Whycron de-duplicates by
            (monitor_id, external_id). Use a job-run ID from your CI.
        :param metadata: Free-form key/value blob, max 8KB encoded.
        :return: Whycron's response — ``{"status": "ok", "run_id": "..."}``.
        """
        path_parts = [f"/p/{ping_token}"]
        if state != "succeeded":
            path_parts.append(state)
        if external_id:
            if state == "succeeded":
                path_parts.append("succeeded")
            path_parts.append(external_id)
        path = "/".join(path_parts)

        payload: dict[str, Any] = {}
        if exit_code is not None:
            payload["exit_code"] = exit_code
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if logs is not None:
            payload["logs"] = logs
        if metadata is not None:
            payload["metadata"] = dict(metadata)

        response = self._client.post(path, json=payload or None)
        return self._unwrap(response)

    # ── monitors ─────────────────────────────────────────────────────────────

    def list_monitors(
        self,
        *,
        status: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if tag:
            params["tag"] = tag
        if search:
            params["search"] = search
        return self._authed_request("GET", "/api/v1/monitors", params=params)

    def create_monitor(
        self,
        *,
        name: str,
        schedule_type: ScheduleType,
        schedule_value: str,
        timezone: str = "UTC",
        grace_period_seconds: int = 60,
        expected_runtime_seconds: int | None = None,
        tags: Iterable[str] | None = None,
        notification_settings: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "schedule_type": schedule_type,
            "schedule_value": schedule_value,
            "timezone": timezone,
            "grace_period_seconds": grace_period_seconds,
        }
        if expected_runtime_seconds is not None:
            body["expected_runtime_seconds"] = expected_runtime_seconds
        if tags is not None:
            body["tags"] = list(tags)
        if notification_settings is not None:
            body["notification_settings"] = dict(notification_settings)
        return self._authed_request("POST", "/api/v1/monitors", json=body)

    def get_monitor(self, monitor_id: str) -> dict[str, Any]:
        return self._authed_request("GET", f"/api/v1/monitors/{monitor_id}")

    def update_monitor(self, monitor_id: str, **fields: Any) -> dict[str, Any]:
        if not fields:
            raise ValueError("update_monitor requires at least one field to change")
        return self._authed_request(
            "PATCH", f"/api/v1/monitors/{monitor_id}", json=fields
        )

    def delete_monitor(self, monitor_id: str) -> None:
        self._authed_request("DELETE", f"/api/v1/monitors/{monitor_id}")

    # ── runs ─────────────────────────────────────────────────────────────────

    def list_runs(
        self,
        *,
        monitor_id: str | None = None,
        state: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if monitor_id:
            params["monitor_id"] = monitor_id
        if state:
            params["state"] = state
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        return self._authed_request("GET", "/api/v1/runs", params=params)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._authed_request("GET", f"/api/v1/runs/{run_id}")

    # ── internals ────────────────────────────────────────────────────────────

    def _authed_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise WhycronAPIError(
                0,
                "api_key is required for this method. Pass it to Whycron(api_key=...).",
            )
        response = self._client.request(
            method,
            path,
            params=params,
            json=json,
            headers={"X-Whycron-API-Key": self._api_key},
        )
        return self._unwrap(response)

    @staticmethod
    def _unwrap(response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 204:
            return {}
        if response.status_code < 400:
            if not response.content:
                return {}
            return response.json()

        try:
            body = response.json()
            detail = body.get("detail") if isinstance(body, dict) else None
            message = detail or response.text or response.reason_phrase
        except ValueError:
            body = response.text
            message = response.text or response.reason_phrase

        if response.status_code == 401:
            raise WhycronAuthError(401, str(message), body)
        if response.status_code == 404:
            raise WhycronNotFoundError(404, str(message), body)
        if response.status_code == 429:
            raise WhycronRateLimitedError(429, str(message), body)
        raise WhycronAPIError(response.status_code, str(message), body)
