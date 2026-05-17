"""SQLAlchemy model registry.

Importing this module is what registers every model against
``apps.api.db.Base.metadata``. Alembic's ``env.py`` imports this package
so ``--autogenerate`` sees the full schema.
"""
from __future__ import annotations

from apps.api.models.api_key import APIKey
from apps.api.models.audit import AuditLog
from apps.api.models.billing import ProcessedPolarEvent
from apps.api.models.monitor import Monitor
from apps.api.models.notification import (
    NotificationChannel,
    NotificationDelivery,
)
from apps.api.models.run import AIExplanation, Run
from apps.api.models.tenancy import Organization, User

__all__ = [
    "APIKey",
    "AIExplanation",
    "AuditLog",
    "Monitor",
    "NotificationChannel",
    "NotificationDelivery",
    "Organization",
    "ProcessedPolarEvent",
    "Run",
    "User",
]
