"""Settings loaded from environment / .env via pydantic-settings.

All secrets and runtime configuration enter the application here. CONTEXT.md
§7.1 forbids reading secrets from any other source. Reference `.env.example`
for the complete variable list.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
AppEnv = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: AppEnv = "development"
    app_url: str = "http://localhost:8000"
    # Dashboard / SPA origin. The backend builds redirect URLs (OAuth
    # callback, billing checkout success) from this, NOT from ``app_url``,
    # because the API and the frontend live on different ports / domains.
    frontend_url: str = "http://localhost:5173"
    app_port: int = 8000
    log_level: LogLevel = "INFO"

    # ── Storage ──────────────────────────────────────────────────────────────
    # Plain `postgresql://` URLs are accepted; the async driver prefix is
    # added by `apps.api.db._async_url`.
    database_url: str = (
        "postgresql://whycron:whycron_local_dev@localhost:5432/whycron"
    )
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth (Supabase) ──────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    # Optional: only needed if your Supabase project signs JWTs with HS256.
    # New projects on RS256 do not need this — verification uses the JWKS
    # endpoint at /auth/v1/.well-known/jwks.json.
    supabase_jwt_secret: str = ""

    # ── LLM (Anthropic) ──────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model_default: str = "claude-haiku-4-5-20251001"
    anthropic_model_premium: str = "claude-sonnet-4-6"

    # ── Email (Brevo) ────────────────────────────────────────────────────────
    brevo_api_key: str = ""
    brevo_sender_email: str = "alerts@whycron.dev"
    brevo_sender_name: str = "Whycron"

    # ── Payments (Polar.sh) ──────────────────────────────────────────────────
    polar_api_key: str = ""
    polar_webhook_secret: str = ""
    polar_product_pro_id: str = ""
    polar_product_team_id: str = ""
    # Default to the sandbox host. Switch to ``https://api.polar.sh`` once
    # the production account is KYC-approved (DECISIONS.md #19 placeholder).
    polar_api_base: str = "https://sandbox-api.polar.sh"

    # ── Error tracking (Sentry) ──────────────────────────────────────────────
    sentry_dsn: str = ""
    sentry_environment: str = "development"

    # ── Analytics (PostHog) ──────────────────────────────────────────────────
    posthog_api_key: str = ""
    posthog_host: str = "https://app.posthog.com"

    # ── Security ─────────────────────────────────────────────────────────────
    webhook_signing_secret: str = ""
    jwt_audience: str = "whycron-api"
    encryption_key: str = ""

    # ── Slack (V2) ───────────────────────────────────────────────────────────
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def _load() -> Settings:
    return Settings()


settings: Settings = _load()
