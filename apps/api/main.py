"""Whycron API entrypoint.

Composes the ping service and the dashboard API into a single FastAPI app
(per CONTEXT.md §4.3 — they are split logically, but a single process in
V1+V2). Routes land in `apps/api/routes/*` in Phase 2 onwards.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

from apps.api.config import settings
from apps.api.db import db
from apps.api.redis_client import redis_client
from apps.api.routes import (
    account,
    api_keys,
    auth,
    billing,
    channels,
    integrations,
    monitors,
    ping,
    runs,
)


def _configure_logging() -> None:
    """Configure structlog for JSON output (CONTEXT.md §4.2.9)."""
    level = getattr(logging, settings.log_level)
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _configure_sentry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=0.1,
        integrations=[FastApiIntegration(), AsyncioIntegration()],
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    _configure_sentry()
    log = structlog.get_logger("whycron.api")
    log.info("startup", env=settings.app_env, app_url=settings.app_url)
    await db.connect()
    await redis_client.connect()
    try:
        yield
    finally:
        log.info("shutdown")
        await db.disconnect()
        await redis_client.disconnect()


app = FastAPI(
    title="Whycron API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/api/v1/openapi.json" if not settings.is_production else None,
)

# CORS (CONTEXT.md §7.8). Restrictive — explicit allowlist only.
_allowed_origins = ["http://localhost:5173"]
if settings.is_production:
    # TODO(saksham): replace with the production dashboard origin once the
    # frontend is deployed (likely https://whycron.dev).
    _allowed_origins.append("https://whycron.dev")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Whycron-API-Key"],
)

app.include_router(ping.router)
app.include_router(auth.router)
app.include_router(monitors.router)
app.include_router(runs.router)
app.include_router(channels.router)
app.include_router(account.router)
app.include_router(billing.router)
app.include_router(api_keys.router)
app.include_router(integrations.router)


@app.get("/health", tags=["meta"])
async def health() -> JSONResponse:
    """Liveness + dependency check (CONTEXT.md §7.10).

    Required deps for the API to function: Postgres + Redis. The Anthropic key
    is reported as an informational check — its absence does not fail health,
    because the LLM call lives in the worker, not the API hot path. A real
    Anthropic round-trip is intentionally not performed here (cost + latency).
    """
    db_ok = await db.healthy()
    redis_ok = await redis_client.healthy()
    anthropic_ok = bool(
        settings.anthropic_api_key
        and settings.anthropic_api_key.startswith("sk-ant-")
    )

    required_ok = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if required_ok else 503,
        content={
            "status": "ok" if required_ok else "degraded",
            "checks": {
                "db": db_ok,
                "redis": redis_ok,
                "anthropic_key_present": anthropic_ok,
            },
        },
    )
