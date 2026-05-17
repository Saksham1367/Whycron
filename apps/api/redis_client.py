"""Async Redis client wrapper.

Used for: ping rate-limiting, RQ queues, ephemeral cache. Never used as
primary storage (CONTEXT.md §3.2).
"""
from __future__ import annotations

import structlog
from redis.asyncio import Redis, from_url

from apps.api.config import settings

log = structlog.get_logger("whycron.redis")


class RedisClient:
    def __init__(self) -> None:
        self._client: Redis | None = None

    async def connect(self) -> None:
        self._client = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        log.info("redis_connected")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            log.info("redis_disconnected")

    @property
    def client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("Redis is not connected")
        return self._client

    async def healthy(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except Exception as exc:
            log.warning("redis_health_failed", error=str(exc))
            return False


redis_client = RedisClient()
