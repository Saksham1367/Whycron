"""Thin wrapper around Alembic.

Usage:
    uv run python scripts/migrate.py upgrade head
    uv run python scripts/migrate.py revision --autogenerate -m "add monitors"
    uv run python scripts/migrate.py downgrade -1
    uv run python scripts/migrate.py current

Equivalent to invoking `alembic` directly with the same arguments. This file
exists so the project has a single named entry point for migrations and a
stable place to add pre/post hooks later (for example, a backup-before-upgrade
hook in production).
"""
from __future__ import annotations

import sys

from alembic.config import main as alembic_main

if __name__ == "__main__":
    sys.exit(alembic_main(argv=sys.argv[1:]))
