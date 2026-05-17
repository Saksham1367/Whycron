# Security policy

## Reporting a vulnerability

If you have discovered a security issue in Whycron, please report it privately.

<!-- TODO(saksham): replace with the public security contact email before launch. -->
**Contact:** _security contact pending_ — please open a private GitHub Security Advisory in the meantime. Do **not** file a public issue.

We acknowledge reports within 48 hours and aim to triage within 5 business days.

## Scope

In scope:
- Anything reachable at the product domain.
- The ping endpoint and the dashboard API.
- The open-source self-host bundle (when published in V2).
- The published SDKs (when released in V2).

Out of scope:
- Third-party services we depend on (Supabase, Polar.sh, Anthropic, Brevo, Cloudflare, DigitalOcean, Sentry, PostHog) — please report those upstream.
- Denial-of-service or volumetric attacks.

## Safe harbour

Good-faith research that follows this policy will not be pursued legally. Do not access data that is not your own, do not disrupt service, and give us reasonable time to remediate before public disclosure.

## Hardening overview

Whycron's mandatory security controls are codified in `CONTEXT.md` §7. Highlights:

- **Log redaction** — every user log payload passes through a multi-pattern redactor before storage and before being sent to the LLM.
- **SSRF-safe webhook delivery** — outbound webhook URLs are validated against private/metadata IP ranges and HTTPS-only.
- **HMAC-verified Polar.sh webhooks** — with timestamp tolerance and idempotency.
- **Parameterized SQL only** — SQLAlchemy ORM throughout.
- **Encrypted-at-rest** user webhook secrets.
- **Per-tier rate limits** on the ping endpoint, enforced in Redis.
- **Soft deletes only** — no hard `DELETE` from app code.

New patterns are added to the redactor as they are discovered. Customer report → patch → release notes.
