"""Per-monitor sliding-window rate limit for the ping endpoint.

CONTEXT.md §6.3: 60/min on free, 600/min on Pro. Implemented with a Redis
sorted set keyed by monitor — score = arrival timestamp, member = unique
per request. Each ping is one ZADD + one ZREMRANGEBYSCORE + one ZCARD,
pipelined for a single round-trip.
"""
from __future__ import annotations

import time
import uuid

from fastapi import HTTPException, status

from apps.api.redis_client import redis_client

_LIMIT_PER_MIN: dict[str, int] = {
    "free": 60,
    "pro": 600,
    "team": 600,
    "business": 600,
    "enterprise": 600,
}
_WINDOW_SECONDS = 60


def limit_for_tier(tier: str) -> int:
    return _LIMIT_PER_MIN.get(tier, _LIMIT_PER_MIN["free"])


async def check_ping_rate_limit(monitor_id: uuid.UUID, tier: str) -> None:
    """Raise 429 if the monitor has exceeded its tier's per-minute limit.

    Each call records itself, prunes entries older than the window, and
    counts the live entries. ``EXPIRE`` keeps the key from leaking when the
    monitor goes idle.
    """
    limit = limit_for_tier(tier)
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    key = f"rl:ping:{monitor_id}"
    member = f"{now}:{uuid.uuid4().hex}"

    pipe = redis_client.client.pipeline()
    pipe.zadd(key, {member: now})
    pipe.zremrangebyscore(key, 0, cutoff)
    pipe.zcard(key)
    pipe.expire(key, _WINDOW_SECONDS * 2)
    _, _, count, _ = await pipe.execute()

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
