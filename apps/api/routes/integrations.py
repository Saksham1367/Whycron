"""Third-party integration OAuth flows. V2 ships with Slack only.

Two routes per integration:

- ``GET /api/v1/integrations/slack/install`` — returns the Slack
  authorize URL. Embeds a one-shot state token in the URL; the same
  token is stored in Redis with a 10-minute TTL. JWT-authenticated; only
  the dashboard owner can connect a workspace.

- ``GET /api/v1/integrations/slack/callback`` — Slack redirects the
  user's browser here after they click "Allow". We verify the state,
  exchange the code for a bot token, encrypt + persist the token, and
  redirect the user back to ``${FRONTEND_URL}/channels?connected=slack``.

The signing secret is reserved for future bot-event ingestion (e.g.
``/whycron`` slash commands in V3); we don't use it in V2.
"""
from __future__ import annotations

import secrets
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from apps.api.config import settings
from apps.api.db import db
from apps.api.models import SlackInstallation
from apps.api.redis_client import redis_client
from apps.api.routes.auth import require_scope
from apps.api.services.auth import AuthedUser
from apps.api.services.crypto import decrypt, encrypt

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
log = structlog.get_logger("whycron.integrations")

_SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_SLACK_OAUTH_ACCESS_URL = "https://slack.com/api/oauth.v2.access"
_SLACK_CONVERSATIONS_LIST_URL = "https://slack.com/api/conversations.list"
_SLACK_OAUTH_SCOPES = "chat:write,chat:write.public,channels:read,groups:read"
_STATE_TTL_SECONDS = 600
_STATE_REDIS_PREFIX = "slack_oauth_state:"


# ── Start ────────────────────────────────────────────────────────────────────


def _slack_redirect_uri() -> str:
    return f"{settings.app_url.rstrip('/')}/api/v1/integrations/slack/callback"


@router.get("/slack/install")
async def slack_install(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> dict[str, str]:
    """Return the Slack authorize URL. Frontend opens it in a top-level
    redirect; Slack will redirect back to ``/slack/callback``."""
    if not settings.slack_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack is not configured on this Whycron instance.",
        )

    state = secrets.token_urlsafe(32)
    await redis_client.client.set(
        _STATE_REDIS_PREFIX + state,
        str(auth.organization_id),
        ex=_STATE_TTL_SECONDS,
    )

    params = {
        "client_id": settings.slack_client_id,
        "scope": _SLACK_OAUTH_SCOPES,
        "redirect_uri": _slack_redirect_uri(),
        "state": state,
    }
    return {"authorize_url": f"{_SLACK_AUTHORIZE_URL}?{urlencode(params)}"}


# ── Callback ─────────────────────────────────────────────────────────────────


@router.get("/slack/callback", include_in_schema=False)
async def slack_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Slack browser redirect handler. Always ends in a redirect back to the
    frontend (success or failure) so the user sees something sensible."""
    frontend = settings.frontend_url.rstrip("/")

    if error:
        log.info("slack_oauth_user_denied", error=error)
        return RedirectResponse(
            f"{frontend}/channels?slack_error={error}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not code or not state:
        return RedirectResponse(
            f"{frontend}/channels?slack_error=missing_code_or_state",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    org_id = await _consume_state(state)
    if org_id is None:
        return RedirectResponse(
            f"{frontend}/channels?slack_error=state_expired",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        access = await _exchange_code_for_token(code)
    except SlackOAuthError as exc:
        log.warning("slack_oauth_exchange_failed", error=str(exc))
        return RedirectResponse(
            f"{frontend}/channels?slack_error=exchange_failed",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    async with db.session() as session:
        existing = (
            await session.execute(
                select(SlackInstallation).where(
                    SlackInstallation.organization_id == org_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.team_id = access["team_id"]
            existing.team_name = access["team_name"]
            existing.bot_user_id = access["bot_user_id"]
            existing.bot_token_encrypted = encrypt(access["bot_token"])
            existing.scopes = access["scopes"]
            existing.app_id = access["app_id"]
            existing.authed_user_id = access.get("authed_user_id")
            existing.deleted_at = None
        else:
            session.add(
                SlackInstallation(
                    organization_id=org_id,
                    team_id=access["team_id"],
                    team_name=access["team_name"],
                    bot_user_id=access["bot_user_id"],
                    bot_token_encrypted=encrypt(access["bot_token"]),
                    scopes=access["scopes"],
                    app_id=access["app_id"],
                    authed_user_id=access.get("authed_user_id"),
                )
            )
        await session.commit()

    log.info(
        "slack_oauth_installed",
        org_id=str(org_id),
        team_name=access["team_name"],
        scopes=access["scopes"],
    )
    return RedirectResponse(
        f"{frontend}/channels?connected=slack",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── Installation info + uninstall ────────────────────────────────────────────


@router.get("/slack")
async def slack_installation_info(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> dict[str, Any]:
    """Returns the current org's Slack workspace, if connected."""
    async with db.session() as session:
        row = (
            await session.execute(
                select(SlackInstallation).where(
                    SlackInstallation.organization_id == auth.organization_id,
                    SlackInstallation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    if row is None:
        return {"connected": False}
    return {
        "connected": True,
        "team_id": row.team_id,
        "team_name": row.team_name,
        "scopes": row.scopes.split(",") if row.scopes else [],
        "installed_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/slack", status_code=status.HTTP_204_NO_CONTENT)
async def slack_uninstall(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> None:
    """Soft-disconnect: mark the install as deleted. Existing Slack
    notification channels will start failing on next dispatch (and we'll
    show that in the deliveries log). The user can reconnect anytime."""
    async with db.session() as session:
        row = (
            await session.execute(
                select(SlackInstallation).where(
                    SlackInstallation.organization_id == auth.organization_id,
                    SlackInstallation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        from datetime import datetime, timezone

        row.deleted_at = datetime.now(timezone.utc)
        await session.commit()


# ── Channel list ─────────────────────────────────────────────────────────────


@router.get("/slack/channels")
async def slack_channels(
    auth: AuthedUser = Depends(require_scope("admin")),
) -> dict[str, Any]:
    """Proxy to ``conversations.list`` so the frontend can render a
    channel picker without us shipping the bot token to the browser.

    Returns public channels + private channels the bot is a member of.
    """
    async with db.session() as session:
        install = (
            await session.execute(
                select(SlackInstallation).where(
                    SlackInstallation.organization_id == auth.organization_id,
                    SlackInstallation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if install is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Slack workspace connected for this organization.",
        )

    bot_token = decrypt(install.bot_token_encrypted)
    channels: list[dict[str, Any]] = []
    cursor: str | None = None

    # conversations.list is paginated; iterate until we have everything,
    # but cap at 10 pages (10 * 200 = 2000 channels) so a huge workspace
    # can't stall the request.
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(10):
            params: dict[str, Any] = {
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor
            response = await client.get(
                _SLACK_CONVERSATIONS_LIST_URL,
                params=params,
                headers={"Authorization": f"Bearer {bot_token}"},
            )
            body = response.json()
            if not body.get("ok"):
                err = body.get("error", "unknown")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Slack rejected channels.list: {err}",
                )
            for ch in body.get("channels", []):
                channels.append(
                    {
                        "id": ch["id"],
                        "name": ch.get("name") or ch["id"],
                        "is_private": ch.get("is_private", False),
                        "is_member": ch.get("is_member", False),
                    }
                )
            cursor = (body.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                break

    channels.sort(key=lambda c: c["name"])
    return {"team_name": install.team_name, "channels": channels}


# ── internals ────────────────────────────────────────────────────────────────


class SlackOAuthError(RuntimeError):
    """oauth.v2.access returned a non-ok response."""


async def _consume_state(state: str) -> uuid.UUID | None:
    raw = await redis_client.client.get(_STATE_REDIS_PREFIX + state)
    if raw is None:
        return None
    # One-shot — delete after first read to prevent replay.
    await redis_client.client.delete(_STATE_REDIS_PREFIX + state)
    try:
        # Redis is configured with decode_responses=True, so values come back
        # as ``str`` — no need to .decode() here.
        return uuid.UUID(raw if isinstance(raw, str) else raw.decode())
    except (ValueError, TypeError):
        return None


async def _exchange_code_for_token(code: str) -> dict[str, Any]:
    """Call ``oauth.v2.access`` and return a normalized dict."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            _SLACK_OAUTH_ACCESS_URL,
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": _slack_redirect_uri(),
            },
        )
    body = response.json()
    if not body.get("ok"):
        raise SlackOAuthError(f"Slack rejected: {body.get('error')}")

    team = body.get("team") or {}
    bot_user_id = body.get("bot_user_id")
    bot_token = body.get("access_token")
    authed_user = body.get("authed_user") or {}
    scopes = body.get("scope") or ""
    app_id = body.get("app_id") or ""

    if not (team.get("id") and bot_user_id and bot_token):
        raise SlackOAuthError(
            f"Slack response missing required fields: {body!r}"
        )

    return {
        "team_id": team["id"],
        "team_name": team.get("name") or team["id"],
        "bot_user_id": bot_user_id,
        "bot_token": bot_token,
        "scopes": scopes,
        "app_id": app_id,
        "authed_user_id": authed_user.get("id"),
    }
