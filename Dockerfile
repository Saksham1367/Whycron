# syntax=docker/dockerfile:1.7
#
# Whycron — production image.
# Builds a single image that can run either the API (default) or the worker,
# selected via the start command. Uses uv for fast, reproducible installs.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"
WORKDIR /app

# Pull a fixed uv binary into the image. Pin the tag here for reproducibility.
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /uvx /usr/local/bin/

# ── deps stage: install dependencies into a cached layer ──────────────────────
FROM base AS deps
COPY pyproject.toml uv.lock* ./
# `--frozen` requires a lockfile; fall back to a fresh resolve if absent
# (first build on CI before the lockfile is committed).
ARG UV_EXTRA=api
RUN --mount=type=cache,target=/root/.cache/uv \
    (uv sync --frozen --no-install-project --extra ${UV_EXTRA} \
     || uv sync --no-install-project --extra ${UV_EXTRA})

# ── runtime stage: copy source and run ────────────────────────────────────────
FROM deps AS app
COPY apps/ apps/
COPY packages/ packages/
COPY scripts/ scripts/
COPY alembic.ini .

EXPOSE 8000

# Override CMD when running the worker:
#   docker run … <image> uv run python -m apps.worker.main
CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
