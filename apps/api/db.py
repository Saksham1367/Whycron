"""Async SQLAlchemy engine and session factory.

Multi-tenancy reminder (CLAUDE.md rule 3): every query against the application
tables MUST filter by `organization_id`. There is no row-level security at the
database layer in V1 — enforcement lives in the repository / service layer
that lands in Phase 1.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from apps.api.config import settings

log = structlog.get_logger("whycron.db")


class Base(DeclarativeBase):
    """Declarative base for every Whycron SQLAlchemy model.

    Models land in `apps/api/models/*` in Phase 1. Importing them at startup
    is what registers their metadata for Alembic autogenerate.
    """


def _async_url(url: str) -> str:
    """Translate a plain `postgresql://` URL to the asyncpg driver form."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class Database:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        url = _async_url(settings.database_url)
        self._engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=10,
            echo=False,
        )
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )
        log.info("db_connected")

    async def disconnect(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
            log.info("db_disconnected")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError("Database is not connected")
        async with self._sessionmaker() as s:
            yield s

    async def healthy(self) -> bool:
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            log.warning("db_health_failed", error=str(exc))
            return False


db = Database()
