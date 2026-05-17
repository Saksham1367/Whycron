"""SSRF guard unit tests (CONTEXT.md §7.3)."""
from __future__ import annotations

import socket
from unittest import mock

import pytest

from apps.api.services.notify.ssrf import (
    UnsafeWebhookURL,
    validate_webhook_url,
)


def _fake_resolves_to(*ips: str):
    """Build a getaddrinfo replacement that returns the given IP strings."""
    def fake(host, port, *_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, port)) for ip in ips
        ]

    return fake


def test_rejects_http_scheme() -> None:
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("http://example.com/webhook")


def test_rejects_other_schemes() -> None:
    for url in (
        "ftp://example.com/x",
        "file:///etc/passwd",
        "ssh://x@example.com",
        "//example.com",
    ):
        with pytest.raises(UnsafeWebhookURL):
            validate_webhook_url(url)


def test_rejects_missing_host() -> None:
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("https:///path")


def test_rejects_metadata_hostnames() -> None:
    for host in (
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.azure.com",
        "instance-data",
        "localhost",
    ):
        with pytest.raises(UnsafeWebhookURL):
            validate_webhook_url(f"https://{host}/x")


@pytest.mark.parametrize(
    "ip",
    [
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.5",
        "172.31.255.254",
        "192.168.0.1",
        "192.168.255.255",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.42.42",  # link-local
        "224.0.0.1",  # multicast
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 unique-local (private)
    ],
)
def test_rejects_non_public_resolutions(ip: str) -> None:
    with mock.patch("socket.getaddrinfo", side_effect=_fake_resolves_to(ip)):
        with pytest.raises(UnsafeWebhookURL):
            validate_webhook_url("https://attacker.example/x")


def test_accepts_public_resolution() -> None:
    with mock.patch(
        "socket.getaddrinfo", side_effect=_fake_resolves_to("93.184.216.34")
    ):
        validate_webhook_url("https://example.com/webhook")  # must not raise


def test_rejects_when_any_resolved_ip_is_private() -> None:
    """If DNS returns multiple IPs and one is private, reject — attackers
    can craft DNS records that mix public + private to bypass naive checks."""
    with mock.patch(
        "socket.getaddrinfo",
        side_effect=_fake_resolves_to("93.184.216.34", "10.0.0.5"),
    ):
        with pytest.raises(UnsafeWebhookURL):
            validate_webhook_url("https://mixed.example/x")


def test_rejects_unresolvable_host() -> None:
    with mock.patch(
        "socket.getaddrinfo",
        side_effect=socket.gaierror("no such host"),
    ):
        with pytest.raises(UnsafeWebhookURL):
            validate_webhook_url("https://nonexistent.example.invalid/x")
