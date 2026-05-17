"""SSRF guard for outbound webhook URLs (CONTEXT.md §7.3).

User-supplied webhook URLs are the single most dangerous input we accept,
because we'll happily POST whatever JSON we have to whatever URL the user
configured. If the user (or an attacker who compromised the dashboard)
configures `http://169.254.169.254/...`, we'd hand cloud instance
credentials to them.

Defenses applied here:

- HTTPS-only.
- Hostname must resolve to a public IPv4/IPv6 address. Any private,
  loopback, link-local, multicast, reserved, or unspecified address
  rejects the URL.
- A hard-coded denylist catches metadata-service hostnames even if DNS
  hasn't resolved them yet.
- DNS is re-checked at send time (callers don't cache resolutions).

Callers must additionally pass ``follow_redirects=False`` to httpx so
3xx responses can't smuggle a redirect to a private IP after the guard
has cleared.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeWebhookURL(ValueError):
    """Raised when a webhook URL fails the SSRF guard."""


_BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        # AWS / GCP / Azure / DigitalOcean metadata
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.azure.com",
        "instance-data",
        "metadata",
        # Loopback aliases
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
    }
)


def validate_webhook_url(url: str) -> None:
    """Raise ``UnsafeWebhookURL`` if ``url`` violates the SSRF policy."""
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise UnsafeWebhookURL(
            f"URL must use https:// (got scheme {parsed.scheme!r})"
        )

    host = parsed.hostname
    if not host:
        raise UnsafeWebhookURL("URL has no host component")

    host_lc = host.lower().rstrip(".")
    if host_lc in _BLOCKED_HOSTS:
        raise UnsafeWebhookURL(f"hostname {host!r} is on the denylist")

    port = parsed.port or 443

    try:
        addrs = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeWebhookURL(f"DNS lookup failed for {host!r}: {exc}") from exc

    if not addrs:
        raise UnsafeWebhookURL(f"DNS returned no addresses for {host!r}")

    for info in addrs:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise UnsafeWebhookURL(f"Could not parse resolved address {ip_str!r}")
        if not _is_publicly_routable(ip):
            raise UnsafeWebhookURL(
                f"{host!r} resolves to non-public address {ip_str}"
            )


def _is_publicly_routable(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback:
        return False
    if ip.is_link_local:
        return False
    if ip.is_multicast:
        return False
    if ip.is_unspecified:
        return False
    if ip.is_reserved:
        return False
    if ip.is_private:
        return False
    # `is_private` covers RFC1918 for IPv4 and unique-local fc00::/7 for IPv6.
    return True
