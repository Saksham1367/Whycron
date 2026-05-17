# Privacy policy (draft)

> This is a working draft. The published policy will replace this file before launch and be reviewed against applicable law (GDPR, CCPA, India DPDP Act).

## Who we are

Whycron is operated by Forgebit. <!-- TODO(saksham): legal entity registration details + privacy contact email -->

## What we collect

- **Account data:** email, name, organization name, billing tier. Stored in Postgres and in Supabase Auth.
- **Monitor data:** cron schedules, monitor names, ping tokens, notification configuration.
- **Run data:** heartbeat pings, exit codes, durations, and the log excerpts you send to our ping endpoint.
- **Diagnostic data:** IP and user-agent on every ping, for abuse detection.
- **Billing data:** handled by Polar.sh as Merchant of Record. We store a customer ID and subscription state, never card numbers.

## What we do with logs

Log excerpts you send are passed through a redactor that strips known secret patterns (cloud provider keys, JWTs, bearer tokens, database connection strings, etc.) before anything is written to our database. Redacted excerpts are stored to power the dashboard and are sent to Anthropic's API to generate the failure explanation that ships with your alert.

Anthropic's API does not train on data submitted through it by default. Logs are not shared across customers. The aggregate failure-pattern features planned for V3 use only deterministic fingerprint hashes — never raw log content.

## Retention

| Data | Free tier | Paid tiers |
|---|---|---|
| Run history | 30 days | 1 year |
| AI explanations | tied to the run | tied to the run |
| Audit log | 1 year | 1 year |
| Backups | 30 days, encrypted at rest | 30 days, encrypted at rest |

After the retention window expires, data is purged automatically.

## Your rights

- **Export:** `GET /api/v1/account/export` returns a ZIP of your data.
- **Deletion:** `POST /api/v1/account/delete` enqueues a purge of all your data within 30 days.
- **Correction:** edit account fields directly in the dashboard.
- **Portability:** the export is machine-readable JSON.

## Subprocessors

| Vendor | Purpose |
|---|---|
| Supabase | Authentication |
| DigitalOcean | Hosting |
| Cloudflare | DNS, TLS, edge protection |
| Polar.sh | Billing (Merchant of Record) |
| Anthropic | LLM-powered failure explanations |
| Brevo | Transactional email |
| Sentry | Error tracking (our own service) |
| PostHog | Product analytics |

## Changes

Material changes will be announced by email to the account owner at least 14 days before taking effect.
