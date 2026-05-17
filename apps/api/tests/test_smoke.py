"""Phase 0 smoke tests — ensure the API import graph is intact.

Phase 1 will add real DB tests that exercise migrations and the model layer.
"""
from __future__ import annotations


def test_app_imports() -> None:
    from apps.api.main import app

    assert app.title == "Whycron API"


def test_health_route_registered() -> None:
    from apps.api.main import app

    paths = {route.path for route in app.routes}
    assert "/health" in paths


def test_async_url_translation() -> None:
    from apps.api.db import _async_url

    assert _async_url("postgresql://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"
    assert _async_url("postgres://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"
    assert (
        _async_url("postgresql+asyncpg://u:p@h/d")
        == "postgresql+asyncpg://u:p@h/d"
    )
