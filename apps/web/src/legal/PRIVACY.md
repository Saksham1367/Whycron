# Privacy Policy

**Effective date:** 2026-05-18
**Last updated:** 2026-05-18

This Privacy Policy explains how Whycron ("Whycron", "we", "us", "our") collects, uses, shares, and protects your information when you use the Whycron service available at whycron.com and related domains (collectively, the "Service"). By using the Service you agree to this Policy.

We have written this in plain English because we want you to actually read it. If anything is unclear, email us at sakshamdhingra1305@gmail.com.

## 1. Who we are

The Service is operated by Saksham Dhingra, an individual residing in Faridabad, Haryana, India ("Operator"), trading under the brand name Whycron. References to "we" / "us" / "our" mean the Operator.

For privacy questions, data subject requests, deletion requests, or to designate a data protection point of contact, write to **sakshamdhingra1305@gmail.com**.

## 2. What we collect

We collect only what we need to run the Service.

**Account data.** Email address, display name, and the OAuth identifier returned by your sign-in provider (Google) or the email/password pair you provide. Stored in our Postgres database and in Supabase Auth.

**Organization data.** Workspace name, slug, plan tier, billing customer ID issued by Polar.

**Monitor configuration.** Monitor names, cron expressions or interval schedules, grace periods, ping tokens, and the notification channels (email address, Slack workspace, Discord webhook, generic webhook URL) you set up.

**Run data.** Each heartbeat ping records the timestamp, exit code, duration in milliseconds, and the log excerpt you send. Log excerpts pass through our redactor (see §4) before any storage or transmission.

**Operational metadata.** Source IP and User-Agent on every ping, for abuse detection and rate limiting.

**Billing data.** Polar.sh acts as Merchant of Record. We store a Polar customer ID and your current subscription state. We never receive, store, or process your card number or full billing address — that is held entirely by Polar.

**Product analytics.** Events that describe how you use the dashboard: page views, sign-up, monitor creation, upgrade clicks, AI-explanation views. We send a stable user UUID and email to PostHog (so we can recognize you across sessions and devices) but never your log excerpts, monitor names, or any content you typed. See §5.

**Error telemetry.** When something breaks in the dashboard or backend we send the stack trace to Sentry. We have configured Sentry with `send_default_pii=false`, so it does not receive user identifiers, IP addresses, request headers, or request bodies — only the code path that failed.

We do not collect your contacts list, location, browsing history, or anything from your device beyond what is described above.

## 3. Why we have the right to process this data

Under GDPR / UK GDPR / India's DPDP Act, processing requires a lawful basis. Our bases are:

- **Performance of a contract** — we need account data, monitor configuration, run data, and billing data to actually run the Service you have signed up for.
- **Legitimate interests** — operational metadata, error telemetry, and product analytics, weighted carefully against your rights, to keep the Service reliable and improve it. You can object to these under §7.
- **Consent** — for any optional marketing communication (we do not currently send any).
- **Legal obligation** — to keep billing records for tax purposes.

## 4. What happens to logs you send

This is the most important section because logs can contain secrets and sensitive output.

**Redaction first.** Every log excerpt is passed through a deterministic redactor *before* it is stored in our database and *before* it is sent to Anthropic. The redactor strips known patterns: cloud provider access keys (AWS, GCP, Azure), JWTs, bearer tokens, OAuth tokens, Slack/Discord tokens, database connection strings with credentials, and email addresses inside connection strings. Redaction is not a substitute for keeping secrets out of logs, but it is a serious second line of defense.

**Redacted excerpts are stored** so the dashboard can show you what failed and so we can re-run the explanation if needed.

**Redacted excerpts are sent to Anthropic** to generate the plain-English failure explanation that ships with your alert. Anthropic's API does not train on data submitted through it by default. Logs are not shared across customers. Anthropic acts as a sub-processor.

**No cross-customer aggregation of raw logs.** Any aggregate-analytics features added in the future will use only deterministic fingerprint hashes — never raw log content.

## 5. Cookies, local storage, and tracking

The dashboard uses:

- **First-party local storage / cookies** for authentication — Supabase Auth stores your session token in browser storage so you stay signed in.
- **PostHog** — sets a first-party cookie and writes to local storage. Configured with `person_profiles: identified_only` so anonymous visitors are not tracked. Session recording is disabled. Autocapture is enabled for click and pageview events.
- **No advertising trackers.** We do not use Google Analytics, Facebook Pixel, ad-network pixels, or cross-site tracking of any kind.
- **No selling of personal data.** We do not sell, rent, or trade personal data, full stop. Under CCPA terminology, we do not "sell" or "share" personal information.

## 6. Subprocessors

We use the following vendors to run the Service. Each receives only the data needed for its role.

| Vendor | Role | Where data is processed | What we send |
|---|---|---|---|
| Supabase (Supabase Inc.) | Authentication | US / EU | Email, OAuth identity, session tokens |
| DigitalOcean | Hosting (Postgres, app servers) | US (East / Central) | All Service data at rest and in transit |
| Cloudflare | DNS, TLS termination, edge protection | Global edge | Request metadata (IP, headers) for transit |
| Polar.sh | Billing & payments (Merchant of Record) | EU | Email, billing details — handled entirely by Polar |
| Anthropic, PBC | LLM-powered failure explanations | US | Redacted log excerpts, monitor name, exit code, duration |
| Brevo (Sendinblue) | Transactional email delivery | EU (France) | Recipient email + the alert body |
| Sentry (Functional Software Inc.) | Error tracking | EU (Frankfurt, Germany) | Stack traces only — no PII |
| PostHog (PostHog Inc.) | Product analytics | US | User UUID, email, event names, page views |

When you add a Slack workspace or Discord webhook, those providers (Slack Technologies LLC, Discord Inc.) also receive the alert content you have configured. Their handling is governed by their own terms.

We will update this list before adding new sub-processors and announce material changes per §10.

## 7. Your rights

You have the following rights over your personal data:

- **Right of access** — request a copy of what we hold on you.
- **Right of rectification** — correct anything wrong. Most fields are editable directly in the dashboard.
- **Right of erasure ("right to be forgotten")** — request deletion of your account and associated data.
- **Right to data portability** — receive your data in a machine-readable format.
- **Right to object** — to processing based on legitimate interests (§3).
- **Right to withdraw consent** — for anything we process on the basis of consent.
- **Right to lodge a complaint** — with your local data protection authority. For users in India, the Data Protection Board of India; for the EU/UK, your country's supervisory authority; for California residents, the California Attorney General.

To exercise any of these, email **sakshamdhingra1305@gmail.com**. We respond within 30 days, free of charge.

The dashboard also provides self-service endpoints:

- `GET /api/v1/account/export` — download a ZIP of all your data.
- `POST /api/v1/account/delete` — schedule full deletion (completed within 30 days).

## 8. Retention

| Data | Free tier | Pro tier |
|---|---|---|
| Run history (heartbeats, exit codes, redacted log excerpts) | 30 days | 1 year |
| AI explanations | Tied to the parent run | Tied to the parent run |
| Audit log (sign-in events, billing events, account changes) | 1 year | 1 year |
| Encrypted database backups | 30 days, then auto-purged | 30 days, then auto-purged |
| Account data (email, name, org) | Until you delete it | Until you delete it |
| Billing records | 7 years, for tax compliance | 7 years, for tax compliance |

After the retention window for a given category expires, data is purged automatically. Account deletion (§7) supersedes these windows and triggers immediate removal of all categories except billing records that we are legally required to retain.

## 9. International data transfers

Whycron is operated from India and uses sub-processors in the United States and the European Union (see §6). When personal data is transferred outside your jurisdiction, the transfer is protected by one of: the sub-processor's Standard Contractual Clauses (SCCs), an adequacy decision, or explicit consent you have given. You may request the specific transfer mechanism for any given sub-processor by emailing us.

## 10. Children

The Service is not directed at children under 16, and we do not knowingly collect personal data from anyone under 16. If you believe a child has signed up, email us and we will delete the account.

## 11. Security

We take security seriously. Highlights:

- All traffic to the Service uses HTTPS (TLS 1.2+).
- Passwords are never stored — authentication is delegated to Supabase Auth.
- Webhook secrets, API tokens, and other secrets are encrypted at rest in the database.
- Polar webhook events are verified by HMAC signature before any state change.
- Database backups are encrypted.
- We run automated dependency vulnerability scanning and address critical advisories promptly.

No system is 100% secure. If you discover a security issue, see SECURITY.md or write to sakshamdhingra1305@gmail.com.

## 12. Changes to this Policy

We may update this Policy. Material changes will be announced by email to the account owner at least 14 days before taking effect. The "Last updated" date at the top reflects the current version. Continued use of the Service after the effective date constitutes acceptance.

## 13. Contact

For any privacy question, request, or complaint:

**Saksham Dhingra**
Operator of Whycron
Faridabad, Haryana, India
**sakshamdhingra1305@gmail.com**
