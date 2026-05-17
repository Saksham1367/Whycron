"""Sliding-window rate limit tests (CONTEXT.md §6.3)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from apps.api.services.ratelimit import (
    check_ping_rate_limit,
    limit_for_tier,
)

# No module-level pytestmark — asyncio_mode=auto handles async tests, and
# applying the asyncio mark to a sync test (limit_for_tier) raises a warning.


def test_limit_for_tier_defaults_to_free() -> None:
    assert limit_for_tier("free") == 60
    assert limit_for_tier("pro") == 600
    assert limit_for_tier("nonsense") == 60


async def test_free_tier_rate_limit_kicks_in_at_61(connected_db: None) -> None:
    monitor_id = uuid.uuid4()
    # 60 calls under the limit succeed.
    for i in range(60):
        await check_ping_rate_limit(monitor_id, "free")

    # The 61st must raise.
    with pytest.raises(HTTPException) as ei:
        await check_ping_rate_limit(monitor_id, "free")
    assert ei.value.status_code == 429


async def test_pro_tier_allows_more(connected_db: None) -> None:
    monitor_id = uuid.uuid4()
    # 100 calls is well under 600.
    for _ in range(100):
        await check_ping_rate_limit(monitor_id, "pro")
    # No exception expected.


async def test_separate_monitors_have_independent_limits(
    connected_db: None,
) -> None:
    a = uuid.uuid4()
    b = uuid.uuid4()
    for _ in range(60):
        await check_ping_rate_limit(a, "free")
    # b should still be fully under its own limit.
    for _ in range(60):
        await check_ping_rate_limit(b, "free")
    with pytest.raises(HTTPException):
        await check_ping_rate_limit(a, "free")
    with pytest.raises(HTTPException):
        await check_ping_rate_limit(b, "free")
