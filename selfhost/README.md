# Whycron — self-host preview

> **Heads up.** This is the **silver** edition of Whycron. The hosted product at [whycron.com](https://whycron.com) is the **diamond** edition and includes features deliberately *not* available here — see [feature comparison](#feature-comparison) below.

A `docker compose up` package that runs the entire Whycron stack on your own infrastructure: API, worker, web dashboard, Postgres, Redis.

## What you get

- Cron / scheduled-job monitoring — heartbeat pings, missed-run detection, timed-out detection
- Notification channels: email (BYO Brevo) + webhook + Discord webhook
- Public status pages (`/status/{slug}`)
- API + API keys; the published [`whycron-sdk`](https://pypi.org/project/whycron-sdk/) (Python) and [`whycron`](https://www.npmjs.com/package/whycron) (Node) SDKs work against your self-hosted instance
- Multi-monitor dashboard with run history and audit log

## What you don't get

- **AI failure explanations** — the headline feature. Available only on [whycron.com](https://whycron.com).
- **Slack OAuth + threaded alerts** — UI hidden. You can still send to Slack via an inbound webhook URL, just without the polished bot.
- **Team management** — single-organization mode. Add users via Supabase and they all share one workspace.
- **Hosted reliability** — backups, patching, uptime are on you.

## Prerequisites

1. **Docker + Docker Compose v2** (Docker Desktop or stock Linux Docker).
2. **A Supabase project** for authentication. Free tier is fine. Setup is 5 minutes:
   - Sign up at https://supabase.com → New project (pick any region close to you).
   - Authentication → Providers → enable Email. Optionally enable Google for OAuth.
   - Authentication → URL Configuration → Site URL: `http://localhost:8080` (or your real URL). Redirect URLs: add `http://localhost:8080/auth/callback`.
   - Settings → API → copy **Project URL** and the **anon / public** key. (Don't copy the service-role key — never paste that anywhere.)

## Quick start

```bash
git clone --branch feature/self-host-docker https://github.com/Saksham1367/Whycron.git
cd Whycron/selfhost

cp .env.example .env
# Edit .env — at minimum set:
#   POSTGRES_PASSWORD, ENCRYPTION_KEY, WEBHOOK_SIGNING_SECRET,
#   SUPABASE_URL, SUPABASE_ANON_KEY
nano .env

# Generate the ENCRYPTION_KEY value:
docker run --rm python:3.12-slim-bookworm python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
  2>/dev/null || true
# (Or run the same one-liner with any local Python that has `cryptography`.)

docker compose up -d --build
```

First build downloads images + compiles the frontend; ~3–5 minutes on a warm Docker cache.

Then open **http://localhost:8080** in your browser. Sign in with the email you registered in Supabase. You'll land in the dashboard with an empty monitor list.

## Smoke test

```bash
# Create a monitor in the dashboard, copy its ping token, then:
curl -X POST "http://localhost:8000/p/<YOUR_PING_TOKEN>/fail" \
     -H "Content-Type: application/json" \
     -d '{"exit_code": 1, "logs": "ERROR: test"}'
```

You should see the run appear in the dashboard within seconds. If you've configured a notification channel pointed at an email / webhook, the alert lands there too — but without the AI explanation (that's diamond-only).

## Configuration reference

See [`.env.example`](.env.example) — every option is documented inline with what it does and what happens if you leave it empty.

## Feature comparison

| | **Self-host (silver)** | **whycron.com (diamond)** |
|---|---|---|
| Heartbeat monitoring | ✅ | ✅ |
| Missed / timed-out detection | ✅ | ✅ |
| Email / webhook / Discord channels | ✅ | ✅ |
| Public status pages | ✅ | ✅ |
| API + API keys + SDKs | ✅ | ✅ |
| AI failure explanations | ❌ | ✅ |
| Slack OAuth + threaded alerts | ❌ (use webhook) | ✅ |
| Team management / multiple orgs | ❌ | ✅ |
| Managed backups | ❌ | ✅ |
| Uptime / on-call | You | Us |

If you want the AI explanations or Slack OAuth, point your jobs at `whycron.com` (or use both — self-host for low-stakes jobs, hosted for production).

## Production tips

- **Reverse proxy.** All compose ports bind to `127.0.0.1`. Put Caddy, nginx, Traefik, or Cloudflare Tunnel in front before exposing to the internet. The web container speaks plain HTTP on port 80; the API speaks plain HTTP on port 8000.
- **Webhook URLs.** When `APP_URL` / `FRONTEND_URL` change, rebuild the web image: `docker compose build web && docker compose up -d`. The Vite bundle bakes those URLs at build time.
- **Backups.** Postgres data lives in the `whycron-postgres` named volume. Standard `pg_dump` works:
  ```bash
  docker compose exec postgres pg_dump -U whycron whycron > backup.sql
  ```
- **Upgrades.** `git pull && docker compose up -d --build`. Migrations run automatically on every API container start.
- **Logs.** `docker compose logs -f api worker`. Both processes emit structured JSON logs.

## Reporting issues

[GitHub issues](https://github.com/Saksham1367/Whycron/issues). Mention you're self-hosting and include your `docker compose ps` output + the relevant container logs.

## License

The Whycron source is MIT-licensed for the SDKs (see `apps/sdks/*/LICENSE`). The self-host build of the main application is provided as-is for evaluation and personal use; **commercial use of the self-host build requires a separate license** until a public open-source decision is made. Email sakshamdhingra1305@gmail.com to discuss.
