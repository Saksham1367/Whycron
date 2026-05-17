# Whycron

> **Cron monitoring that tells you why.**

Same heartbeat reliability you'd trust from Cronitor or Healthchecks — but
when something breaks, Whycron reads your logs and ships a plain-English
root cause and a suggested fix inside the alert. No more SSH-tail-and-guess
at 3am.

---

## What it actually does

Your scheduled job sends a heartbeat ping to Whycron at runtime. If a ping
arrives late, doesn't arrive at all, or arrives with a failure payload,
Whycron records it and decides what to do.

For **failed pings with logs**, an AI (Claude Haiku 4.5) reads the logs
and writes three short paragraphs that ship inside every alert — email,
webhook, or Discord:

> **Root cause.** Job failed because pg_dump encountered ENOSPC (no space
> left on device) while writing the backup file, causing the dump to fail
> and the backup volume to fill completely.
>
> **Explanation.** The backup process initiated normally but ran out of
> disk space during the pg_dump write operation, as evidenced by the
> explicit "No space left on device" error in the logs.
>
> **Suggested fix.** Check the backup volume's current disk usage and
> capacity immediately, then identify what is consuming space. Implement a
> retention policy to delete backups older than a threshold, or increase
> the volume size before the next scheduled run at 02:00 UTC.

Everything above is generated automatically. The operator who got paged
already knows where to look before they finish their coffee.

---

## Features

- **Heartbeat ingestion** with `<50ms p99` — POST/GET to a unique ping URL,
  with optional payload of exit code, duration, and log excerpts.
- **AI failure explanations on every failed run** — three-paragraph format,
  grounded in your actual logs with a confidence grade.
- **Missed-run detection** — schedule scanner runs every 30 seconds, marks
  jobs that didn't fire on time as `missed` and alerts.
- **Stuck-run detection** — jobs that started but never reported finish
  within 2× their expected runtime get a `timed_out` alert.
- **Secret redaction** — every log payload passes a 13-pattern redactor
  (AWS keys, GitHub tokens, JWTs, DB connection strings, PII, credit
  cards, etc.) before storage or being sent to the LLM. Patterns are
  catalogued in `apps/api/services/redactor.py`.
- **Alert delivery** to email (Brevo), HMAC-signed webhooks with SSRF
  guard, and Discord — fan-out per organization, retry with exponential
  backoff.
- **Multi-tenant from day 1** — every row carries `organization_id`,
  every query enforces it.
- **Self-service billing** via Polar.sh as Merchant of Record — handles
  tax compliance globally, supports USD globally from any country.
- **A dark, dense, structural dashboard** built in React + TypeScript,
  designed for engineers at 3am.

## Tech stack

| Layer | Choice |
|---|---|
| API + worker | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · asyncpg |
| Background jobs | APScheduler (schedule scanner) + RQ (analyze, notify queues) |
| Frontend | React 18 · Vite · TypeScript |
| Database | PostgreSQL 16 |
| Cache + queue | Redis 7 |
| LLM | Anthropic Claude Haiku 4.5 |
| Auth | Supabase (Google OAuth + email/password) |
| Email | Brevo |
| Payments | Polar.sh (Merchant of Record) |
| Errors | Sentry |

---

## Quick start (using the hosted product)

Once you have a Whycron account and a monitor created, integrating a job
is one HTTP request. From any cron, k8s CronJob, GitHub Action, Vercel
Cron, AWS EventBridge, systemd timer, or background worker:

```bash
# When the job completes successfully:
curl -fsS https://whycron.dev/p/wcr_yourtoken

# When the job fails — Whycron will analyze the logs:
curl -fsS -X POST https://whycron.dev/p/wcr_yourtoken/fail \
  -H "Content-Type: application/json" \
  -d '{
    "exit_code": 1,
    "duration_ms": 12500,
    "logs": "ERROR pg_dump: write to file failed: ENOSPC"
  }'
```

Within seconds the failure is recorded, the AI explanation is generated,
and the alert lands in whichever channels you configured.

---

## Local development

Prerequisites:
- [`uv`](https://docs.astral.sh/uv/) for Python deps + venv
- Docker Desktop (or Docker engine) for the local Postgres + Redis stack
- Node.js 20+ for the frontend

### Backend (API + worker)

```bash
git clone https://github.com/Saksham1367/Whycron.git
cd Whycron

cp .env.example .env
# Fill in: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY,
# ANTHROPIC_API_KEY, BREVO_API_KEY, POLAR_API_KEY, etc.

docker compose up -d                          # Postgres 16 + Redis 7
uv sync --all-extras                          # install API + worker + dev deps
uv run alembic upgrade head                   # apply migrations
uv run uvicorn apps.api.main:app --reload     # http://localhost:8000

# In another window — the background worker (schedule scanner + AI explainer):
uv run python -m apps.worker.main
```

Health check:

```bash
curl http://localhost:8000/health
```

### Frontend

```bash
cd apps/web
cp .env.example .env
# Fill in VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY (same as backend),
# and VITE_API_URL=http://localhost:8000

npm install
npm run dev          # http://localhost:5173
```

### Running the tests

The full suite covers schemas, redaction, signature verification,
scheduling, dispatch, billing, and live integrations against Anthropic
and Brevo (gated on `ANTHROPIC_API_KEY` and `BREVO_API_KEY`):

```bash
uv run pytest -v
```

---

## Repository layout

```
apps/
├── api/        FastAPI — ping endpoint + dashboard REST API + Polar webhook
│   ├── routes/         (HTTP routes by domain)
│   ├── services/       (redactor, ai_explainer, billing, notify, ratelimit)
│   ├── schemas/        (Pydantic request/response models)
│   ├── models/         (SQLAlchemy 2.0 ORM, multi-tenant)
│   ├── migrations/     (Alembic)
│   └── tests/
├── worker/     APScheduler + RQ — schedule scanner, AI explainer, alert dispatcher
└── web/        React 18 + Vite + TypeScript dashboard

packages/shared/    (cross-app types + schemas)
docs/
├── prompts/        (versioned LLM prompts)
└── eval/           (hand-written failure cases for prompt regression)
scripts/            (operational scripts)
```

---

## Architecture in one paragraph

A user's scheduled job POSTs heartbeat pings to `/p/{token}` on the
FastAPI app. The hot path is <50ms — redact, hash, write one row, return
200. On a failed ping, a job is queued in Redis for the worker process
to consume. The worker calls Anthropic's Claude Haiku with a prompt-cached
system prompt, parses the three-paragraph response, validates citations
against the input logs (downgrading confidence on hallucinations), and
writes an `AIExplanation` row. A second job dispatches the alert across
every enabled notification channel for that organization. Meanwhile,
APScheduler runs every 30 seconds checking which monitors should have
pinged by now — missed schedules synthesize a `missed` run row and
trigger the same alert path.

---

## Status

In active development.

## Security

See [`SECURITY.md`](SECURITY.md) for the security policy and how to
report vulnerabilities responsibly.

## Privacy

See [`PRIVACY.md`](PRIVACY.md) for a draft of the privacy policy.

## License

License terms are being finalized. Until then, treat the source as
all-rights-reserved.

---

Built by [Forgebit](https://forge-bit.dev).
