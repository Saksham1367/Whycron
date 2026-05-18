"""Shared pytest fixtures.

Two flavors of test live here:

- **ORM tests** (Phase 1) use the ``session`` fixture — an isolated engine
  per test, wrapped in a transaction that is rolled back. Tests should use
  ``await session.flush()`` (not ``commit``) so the rollback is effective.

- **HTTP integration tests** (Phase 2+) use ``http_client`` and
  ``seeded_monitor``, which connect the global ``db`` and ``redis_client``
  singletons used by the FastAPI app. The route handlers commit, so these
  tests clean up explicitly in reverse-FK order.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Awaitable, Callable

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from apps.api.config import settings
from apps.api.db import _async_url, db
from apps.api.redis_client import redis_client

# Test JWT secret used to sign HS256 tokens that our verifier accepts when
# ``settings.supabase_jwt_secret`` is monkeypatched to this same value.
DASHBOARD_TEST_JWT_SECRET = (
    "dashboard-test-secret-do-not-use-in-production-32-chars-plus"
)


def _make_dashboard_test_jwt(
    *, sub: str, email: str, name: str | None = "Dash User"
) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "sub": sub,
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
            "email": email,
            "user_metadata": {"full_name": name} if name else {},
        },
        DASHBOARD_TEST_JWT_SECRET,
        algorithm="HS256",
    )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # Function-scoped on purpose: pytest-asyncio gives each test its own
    # event loop, and asyncpg connections cling to the loop they were
    # opened on. A shared engine across tests on Windows ProactorEventLoop
    # raises "Event loop is closed" on the second test.
    eng = create_async_engine(_async_url(settings.database_url), echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        async_session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield async_session
        finally:
            await async_session.close()
            await trans.rollback()


# ── HTTP integration fixtures ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _disable_analytics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never fire real PostHog or Sentry traffic. PostHog's startup
    probe can stall the asyncio loop; Sentry's httpx AsyncTransport leaves
    a dangling ``AsyncClient.aclose()`` task on the pytest event loop after
    teardown, producing noisy "Event loop is closed" warnings. Production
    runs use the real keys from .env."""
    monkeypatch.setattr("apps.api.config.settings.posthog_api_key", "")
    monkeypatch.setattr("apps.api.config.settings.sentry_dsn", "")


@pytest_asyncio.fixture
async def connected_db() -> AsyncIterator[None]:
    """Connect the global ``db`` and ``redis_client`` singletons for tests
    that hit the FastAPI app directly. Function-scoped for the same loop
    reason as ``engine``.
    """
    await db.connect()
    await redis_client.connect()
    try:
        yield
    finally:
        await db.disconnect()
        await redis_client.disconnect()


@pytest_asyncio.fixture
async def http_client(connected_db: None) -> AsyncIterator[AsyncClient]:
    from apps.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seeded_monitor(connected_db: None) -> AsyncIterator[dict[str, object]]:
    """Create a fresh org + monitor for one test, then delete them.

    Returns a dict with ``ping_token``, ``monitor_id``, ``org_id``. Cleanup
    deletes audit_log + runs + monitor + org in reverse-FK order.
    """
    from apps.api.models import AuditLog, Monitor, Organization, Run

    test_id = uuid.uuid4().hex[:12]
    async with db.session() as s:
        org = Organization(
            name="Ping Test",
            slug=f"ptest-{test_id}",
            tier="free",
        )
        s.add(org)
        await s.flush()
        monitor = Monitor(
            organization_id=org.id,
            name=f"Ping Test Monitor {test_id}",
            ping_token=f"wcr_ptest_{test_id}",
            schedule_type="cron",
            schedule_value="*/5 * * * *",
        )
        s.add(monitor)
        await s.commit()
        m_id = monitor.id
        org_id = org.id
        token = monitor.ping_token

    yield {"monitor_id": m_id, "org_id": org_id, "ping_token": token}

    async with db.session() as s:
        await s.execute(
            delete(AuditLog).where(AuditLog.organization_id == org_id)
        )
        await s.execute(delete(Run).where(Run.organization_id == org_id))
        await s.execute(delete(Monitor).where(Monitor.id == m_id))
        await s.execute(delete(Organization).where(Organization.id == org_id))
        await s.commit()


# ── Dashboard auth fixtures ──────────────────────────────────────────────────


AuthedClientFactory = Callable[..., Awaitable[tuple[AsyncClient, dict[str, Any]]]]


@pytest_asyncio.fixture
async def authed_user_factory(
    connected_db: None, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AuthedClientFactory]:
    """Factory: builds an ``(AsyncClient, ctx)`` pair for an authenticated
    Whycron user. Call multiple times in one test for cross-org isolation
    checks. All data created via this fixture is cleaned up after the test.

    ``ctx`` keys: ``user_id``, ``org_id``, ``email``, ``supabase_user_id``.
    """
    from apps.api.main import app
    from apps.api.models import (
        AIExplanation,
        APIKey,
        AuditLog,
        Monitor,
        NotificationChannel,
        NotificationDelivery,
        Organization,
        Run,
        SlackInstallation,
        User,
    )

    monkeypatch.setattr(
        "apps.api.config.settings.supabase_jwt_secret",
        DASHBOARD_TEST_JWT_SECRET,
    )

    created_orgs: list[uuid.UUID] = []
    open_clients: list[AsyncClient] = []

    async def _make(
        *, tier: str = "free", email: str | None = None
    ) -> tuple[AsyncClient, dict[str, Any]]:
        supabase_user_id = str(uuid.uuid4())
        actual_email = (
            email or f"dashtest-{uuid.uuid4().hex[:10]}@authtest.example"
        )

        async with db.session() as s:
            org = Organization(
                name="Dashboard Test Org",
                slug=f"dash-{uuid.uuid4().hex[:10]}",
                tier=tier,
            )
            s.add(org)
            await s.flush()
            user = User(
                organization_id=org.id,
                supabase_user_id=supabase_user_id,
                email=actual_email,
                name="Dash User",
                role="owner",
            )
            s.add(user)
            await s.commit()
            ctx: dict[str, Any] = {
                "user_id": user.id,
                "org_id": org.id,
                "email": actual_email,
                "supabase_user_id": supabase_user_id,
            }
        created_orgs.append(org.id)

        token = _make_dashboard_test_jwt(
            sub=supabase_user_id, email=actual_email
        )
        transport = ASGITransport(app=app)
        client = AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.__aenter__()
        open_clients.append(client)
        return client, ctx

    yield _make

    for c in open_clients:
        await c.__aexit__(None, None, None)

    async with db.session() as s:
        for org_id in created_orgs:
            await s.execute(
                delete(AuditLog).where(AuditLog.organization_id == org_id)
            )
            await s.execute(
                delete(NotificationDelivery).where(
                    NotificationDelivery.organization_id == org_id
                )
            )
            await s.execute(
                delete(NotificationChannel).where(
                    NotificationChannel.organization_id == org_id
                )
            )
            await s.execute(
                delete(AIExplanation).where(
                    AIExplanation.organization_id == org_id
                )
            )
            await s.execute(delete(Run).where(Run.organization_id == org_id))
            await s.execute(
                delete(Monitor).where(Monitor.organization_id == org_id)
            )
            await s.execute(
                delete(APIKey).where(APIKey.organization_id == org_id)
            )
            await s.execute(
                delete(SlackInstallation).where(
                    SlackInstallation.organization_id == org_id
                )
            )
            await s.execute(
                delete(User).where(User.organization_id == org_id)
            )
            await s.execute(
                delete(Organization).where(Organization.id == org_id)
            )
        await s.commit()
