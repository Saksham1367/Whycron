"""Notification channels API tests — CRUD, SSRF guard, multi-tenancy."""
from __future__ import annotations

import socket
from unittest import mock

from sqlalchemy import select

from apps.api.db import db
from apps.api.models import NotificationChannel


def _public_dns_patch():
    """Patch socket.getaddrinfo to return a public IP for any host. Lets
    the SSRF guard pass URLs we use in tests without real DNS."""

    def fake(host, port, *_args, **_kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                0,
                "",
                ("93.184.216.34", port or 443),
            )
        ]

    return mock.patch("socket.getaddrinfo", side_effect=fake)


# ── Create ───────────────────────────────────────────────────────────────────


async def test_create_email_channel(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/notification-channels",
        json={
            "type": "email",
            "name": "Ops Inbox",
            "config": {"to": "ops@example.com"},
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["type"] == "email"
    assert data["config"]["to"] == "ops@example.com"


async def test_create_webhook_channel_with_public_url(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    with _public_dns_patch():
        response = await client.post(
            "/api/v1/notification-channels",
            json={
                "type": "webhook",
                "name": "External Hook",
                "config": {
                    "url": "https://hooks.example.com/whycron",
                    "secret": "topsecret",
                },
            },
        )
    assert response.status_code == 201, response.text


async def test_create_webhook_rejects_private_url(
    authed_user_factory,
) -> None:
    """SSRF: a URL resolving to a private IP must be rejected at create-time."""
    client, _ = await authed_user_factory()

    def fake(host, port, *_args, **_kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                0,
                "",
                ("10.0.0.5", port or 443),
            )
        ]

    with mock.patch("socket.getaddrinfo", side_effect=fake):
        response = await client.post(
            "/api/v1/notification-channels",
            json={
                "type": "webhook",
                "name": "Internal",
                "config": {"url": "https://internal.example.com/x"},
            },
        )
    assert response.status_code == 400
    assert "unsafe" in response.json()["detail"].lower()


async def test_create_webhook_rejects_http_url(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/notification-channels",
        json={
            "type": "webhook",
            "name": "Insecure",
            "config": {"url": "http://example.com/x"},
        },
    )
    # Schema validator rejects before SSRF: requires https://.
    assert response.status_code == 422


async def test_create_slack_is_rejected_for_v1(authed_user_factory) -> None:
    """Slack OAuth lands in V2. Reject channel creation cleanly."""
    client, _ = await authed_user_factory()
    response = await client.post(
        "/api/v1/notification-channels",
        json={
            "type": "slack",
            "name": "Slack Channel",
            "config": {"webhook_url": "https://slack.com/x"},
        },
    )
    assert response.status_code == 422


# ── Read / Update / Delete ───────────────────────────────────────────────────


async def test_create_response_includes_secret_but_get_redacts(
    authed_user_factory,
) -> None:
    client, _ = await authed_user_factory()
    with _public_dns_patch():
        created = (
            await client.post(
                "/api/v1/notification-channels",
                json={
                    "type": "webhook",
                    "name": "Hook",
                    "config": {
                        "url": "https://hooks.example.com/x",
                        "secret": "very-secret-value",
                    },
                },
            )
        ).json()
    assert created["config"]["secret"] == "very-secret-value"

    fetched = (
        await client.get(f"/api/v1/notification-channels/{created['id']}")
    ).json()
    assert fetched["config"]["secret"] == "***"


async def test_list_redacts_secrets(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    with _public_dns_patch():
        await client.post(
            "/api/v1/notification-channels",
            json={
                "type": "webhook",
                "name": "H1",
                "config": {
                    "url": "https://hooks.example.com/x",
                    "secret": "s1",
                },
            },
        )
    listing = await client.get("/api/v1/notification-channels")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert any(c["config"].get("secret") == "***" for c in items)


async def test_update_channel(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    created = (
        await client.post(
            "/api/v1/notification-channels",
            json={
                "type": "email",
                "name": "Inbox",
                "config": {"to": "a@example.com"},
            },
        )
    ).json()
    response = await client.patch(
        f"/api/v1/notification-channels/{created['id']}",
        json={"enabled": False, "name": "Renamed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["name"] == "Renamed"


async def test_delete_channel_soft_deletes(authed_user_factory) -> None:
    client, _ = await authed_user_factory()
    created = (
        await client.post(
            "/api/v1/notification-channels",
            json={
                "type": "email",
                "name": "Inbox",
                "config": {"to": "a@example.com"},
            },
        )
    ).json()
    response = await client.delete(
        f"/api/v1/notification-channels/{created['id']}"
    )
    assert response.status_code == 204

    listing = await client.get("/api/v1/notification-channels")
    assert listing.json()["total"] == 0

    async with db.session() as s:
        row = (
            await s.execute(
                select(NotificationChannel).where(
                    NotificationChannel.id == created["id"]
                )
            )
        ).scalar_one()
    assert row.deleted_at is not None


# ── Multi-tenancy ────────────────────────────────────────────────────────────


async def test_other_org_cannot_see_channels(authed_user_factory) -> None:
    client_a, _ = await authed_user_factory()
    client_b, _ = await authed_user_factory()
    await client_a.post(
        "/api/v1/notification-channels",
        json={
            "type": "email",
            "name": "OrgA inbox",
            "config": {"to": "a@example.com"},
        },
    )
    listing = await client_b.get("/api/v1/notification-channels")
    assert listing.json()["total"] == 0


async def test_other_org_cannot_delete_channel(authed_user_factory) -> None:
    client_a, _ = await authed_user_factory()
    client_b, _ = await authed_user_factory()
    created = (
        await client_a.post(
            "/api/v1/notification-channels",
            json={
                "type": "email",
                "name": "OrgA inbox",
                "config": {"to": "a@example.com"},
            },
        )
    ).json()
    response = await client_b.delete(
        f"/api/v1/notification-channels/{created['id']}"
    )
    assert response.status_code == 404
