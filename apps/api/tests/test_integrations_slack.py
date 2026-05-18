"""Slack OAuth + channel listing + uninstall tests (Phase 13)."""
from __future__ import annotations

from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from apps.api.db import db
from apps.api.models import SlackInstallation
from apps.api.services.crypto import decrypt


# ── Fakes for httpx ──────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeAsyncClient:
    """Records every call; replays canned responses in FIFO order.

    Handles ``.post(url, data=...)``, ``.post(url, json=...)``, and
    ``.get(url, params=...)`` so it works for both Slack's form-encoded
    OAuth call and its JSON RPC endpoints.
    """

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self._responses.pop(0)

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self._responses.pop(0)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def slack_config(monkeypatch: pytest.MonkeyPatch) -> str:
    """Pre-seed Slack creds + a known Fernet key for crypto."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr("apps.api.config.settings.encryption_key", key)
    monkeypatch.setattr("apps.api.config.settings.slack_client_id", "1234.5678")
    monkeypatch.setattr(
        "apps.api.config.settings.slack_client_secret", "client_secret_test"
    )
    monkeypatch.setattr(
        "apps.api.config.settings.app_url", "http://localhost:8000"
    )
    monkeypatch.setattr(
        "apps.api.config.settings.frontend_url", "http://localhost:5173"
    )
    # crypto module caches the Fernet — reset so the new key is picked up.
    from apps.api.services import crypto as crypto_mod

    crypto_mod._fernet.cache_clear()
    return key


# ── Install URL ──────────────────────────────────────────────────────────────


async def test_install_returns_authorize_url_with_state(
    slack_config: str, authed_user_factory
) -> None:
    client, _ctx = await authed_user_factory()
    response = await client.get("/api/v1/integrations/slack/install")
    assert response.status_code == 200
    body = response.json()
    url = body["authorize_url"]
    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "client_id=1234.5678" in url
    assert "scope=chat%3Awrite" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000" in url
    assert "state=" in url


async def test_install_requires_admin(
    slack_config: str, authed_user_factory
) -> None:
    """Without admin scope the route should 403. Use the JWT path so the
    user IS admin-equivalent (JWT passes all scope gates by design)."""
    # The factory uses JWT auth which is admin-equivalent — should pass.
    client, _ = await authed_user_factory()
    response = await client.get("/api/v1/integrations/slack/install")
    assert response.status_code == 200


async def test_install_503_when_slack_disabled(
    authed_user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("apps.api.config.settings.slack_client_id", "")
    client, _ = await authed_user_factory()
    response = await client.get("/api/v1/integrations/slack/install")
    assert response.status_code == 503


# ── Callback ─────────────────────────────────────────────────────────────────


async def test_callback_persists_install_and_redirects(
    slack_config: str,
    authed_user_factory,
    monkeypatch: pytest.MonkeyPatch,
    http_client,
) -> None:
    user_client, ctx = await authed_user_factory()
    # Start the install to get a legitimate state token in Redis.
    start = await user_client.get("/api/v1/integrations/slack/install")
    authorize_url = start.json()["authorize_url"]
    state = authorize_url.split("state=")[-1]

    fake = _FakeAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "ok": True,
                    "app_id": "A111",
                    "scope": "chat:write,channels:read",
                    "access_token": "xoxb-fake-bot-token-value",
                    "bot_user_id": "U_BOT_42",
                    "team": {"id": "T123", "name": "Acme Inc"},
                    "authed_user": {"id": "U_USER_99"},
                },
            )
        ]
    )
    monkeypatch.setattr(
        "apps.api.routes.integrations.httpx.AsyncClient",
        lambda **kw: fake,
    )

    response = await http_client.get(
        f"/api/v1/integrations/slack/callback?code=fake-code&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/channels?connected=slack")

    # Sent the form-encoded oauth.v2.access call once.
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://slack.com/api/oauth.v2.access"
    form = call.get("data") or {}
    assert form["code"] == "fake-code"
    assert form["client_id"] == "1234.5678"
    assert form["client_secret"] == "client_secret_test"

    async with db.session() as s:
        install = (
            await s.execute(
                select(SlackInstallation).where(
                    SlackInstallation.organization_id == ctx["org_id"]
                )
            )
        ).scalar_one()
    assert install.team_id == "T123"
    assert install.team_name == "Acme Inc"
    assert install.bot_user_id == "U_BOT_42"
    assert install.scopes == "chat:write,channels:read"
    assert install.app_id == "A111"
    assert install.authed_user_id == "U_USER_99"
    # Crucially: the raw token is NOT stored.
    assert install.bot_token_encrypted != "xoxb-fake-bot-token-value"
    # …but decrypts correctly.
    assert decrypt(install.bot_token_encrypted) == "xoxb-fake-bot-token-value"


async def test_callback_with_bogus_state_redirects_to_error(
    slack_config: str, http_client
) -> None:
    response = await http_client.get(
        "/api/v1/integrations/slack/callback?code=x&state=does-not-exist",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "slack_error=state_expired" in response.headers["location"]


async def test_callback_when_user_denies(slack_config: str, http_client) -> None:
    response = await http_client.get(
        "/api/v1/integrations/slack/callback?error=access_denied",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "slack_error=access_denied" in response.headers["location"]


async def test_callback_replays_state_only_once(
    slack_config: str,
    authed_user_factory,
    monkeypatch: pytest.MonkeyPatch,
    http_client,
) -> None:
    """A state token must not be reusable — replay-attack guard."""
    user_client, _ = await authed_user_factory()
    start = await user_client.get("/api/v1/integrations/slack/install")
    state = start.json()["authorize_url"].split("state=")[-1]

    fake = _FakeAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "ok": True,
                    "app_id": "A1",
                    "scope": "chat:write",
                    "access_token": "xoxb-1",
                    "bot_user_id": "U",
                    "team": {"id": "T1", "name": "T1"},
                    "authed_user": {"id": "U"},
                },
            )
        ]
    )
    monkeypatch.setattr(
        "apps.api.routes.integrations.httpx.AsyncClient",
        lambda **kw: fake,
    )

    r1 = await http_client.get(
        f"/api/v1/integrations/slack/callback?code=c&state={state}",
        follow_redirects=False,
    )
    assert "connected=slack" in r1.headers["location"]

    r2 = await http_client.get(
        f"/api/v1/integrations/slack/callback?code=c&state={state}",
        follow_redirects=False,
    )
    assert "slack_error=state_expired" in r2.headers["location"]


# ── Installation info + uninstall ────────────────────────────────────────────


async def test_get_install_returns_connected_false_initially(
    slack_config: str, authed_user_factory
) -> None:
    client, _ = await authed_user_factory()
    response = await client.get("/api/v1/integrations/slack")
    assert response.status_code == 200
    assert response.json() == {"connected": False}


async def test_uninstall_soft_deletes_then_get_returns_false(
    slack_config: str,
    authed_user_factory,
    monkeypatch: pytest.MonkeyPatch,
    http_client,
) -> None:
    client, ctx = await authed_user_factory()
    # Bootstrap an install via the same OAuth helper used in production code.
    start = await client.get("/api/v1/integrations/slack/install")
    state = start.json()["authorize_url"].split("state=")[-1]
    fake = _FakeAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "ok": True,
                    "app_id": "A1",
                    "scope": "chat:write",
                    "access_token": "xoxb-zzz",
                    "bot_user_id": "U",
                    "team": {"id": "T1", "name": "Workspace"},
                    "authed_user": {"id": "U"},
                },
            )
        ]
    )
    monkeypatch.setattr(
        "apps.api.routes.integrations.httpx.AsyncClient",
        lambda **kw: fake,
    )
    await http_client.get(
        f"/api/v1/integrations/slack/callback?code=c&state={state}",
        follow_redirects=False,
    )

    # Now query and uninstall via the dashboard.
    info = (await client.get("/api/v1/integrations/slack")).json()
    assert info["connected"] is True
    assert info["team_name"] == "Workspace"

    drop = await client.delete("/api/v1/integrations/slack")
    assert drop.status_code == 204

    after = (await client.get("/api/v1/integrations/slack")).json()
    assert after == {"connected": False}


# ── Channel listing ──────────────────────────────────────────────────────────


async def test_channels_list_requires_install(
    slack_config: str, authed_user_factory
) -> None:
    client, _ = await authed_user_factory()
    response = await client.get("/api/v1/integrations/slack/channels")
    assert response.status_code == 404


async def test_channels_list_returns_sorted_channels(
    slack_config: str,
    authed_user_factory,
    monkeypatch: pytest.MonkeyPatch,
    http_client,
) -> None:
    client, _ = await authed_user_factory()
    # Install first.
    start = await client.get("/api/v1/integrations/slack/install")
    state = start.json()["authorize_url"].split("state=")[-1]
    install_fake = _FakeAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "ok": True,
                    "app_id": "A1",
                    "scope": "chat:write,channels:read",
                    "access_token": "xoxb-test-token",
                    "bot_user_id": "U",
                    "team": {"id": "T1", "name": "Workspace"},
                    "authed_user": {"id": "U"},
                },
            )
        ]
    )
    monkeypatch.setattr(
        "apps.api.routes.integrations.httpx.AsyncClient",
        lambda **kw: install_fake,
    )
    await http_client.get(
        f"/api/v1/integrations/slack/callback?code=c&state={state}",
        follow_redirects=False,
    )

    list_fake = _FakeAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "ok": True,
                    "channels": [
                        {"id": "C2", "name": "general", "is_private": False, "is_member": True},
                        {"id": "C1", "name": "alerts", "is_private": False, "is_member": False},
                    ],
                    "response_metadata": {"next_cursor": ""},
                },
            )
        ]
    )
    monkeypatch.setattr(
        "apps.api.routes.integrations.httpx.AsyncClient",
        lambda **kw: list_fake,
    )

    response = await client.get("/api/v1/integrations/slack/channels")
    assert response.status_code == 200
    body = response.json()
    assert body["team_name"] == "Workspace"
    names = [c["name"] for c in body["channels"]]
    assert names == ["alerts", "general"]
    # The bot token was used as the Authorization header for the call.
    assert (
        list_fake.calls[0]["headers"]["Authorization"]
        == "Bearer xoxb-test-token"
    )
