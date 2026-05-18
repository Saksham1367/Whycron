# whycron — Node.js client for Whycron

Cron job monitoring that tells you why. This is the official Node.js / TypeScript SDK.

```bash
npm install whycron
# or: pnpm add whycron / yarn add whycron / bun add whycron
```

Requires Node 18+ (uses native `fetch`).

## Heartbeat pings

The ping token is the credential — no API key needed.

```ts
import { Whycron } from "whycron";

const wc = new Whycron();

await wc.ping("wcr_abc123def", { state: "started" });
try {
  await doTheWork();
  await wc.ping("wcr_abc123def", { state: "succeeded", durationMs: 1234 });
} catch (err) {
  await wc.ping("wcr_abc123def", {
    state: "failed",
    exitCode: 1,
    logs: String(err),
  });
  throw err;
}
```

## `withMonitor` helper

For most jobs, this is all you need:

```ts
import { Whycron, withMonitor } from "whycron";

const wc = new Whycron();

const nightlyBackup = withMonitor("wcr_abc123def", wc, async () => {
  // your work
});

await nightlyBackup();
```

Sends a `started` ping before the function runs, then `succeeded` (with `exit_code=0` and `duration_ms`) on a clean resolve, or `failed` (with `exit_code=1`, `duration_ms`, and the error stack tail as `logs`) on rejection. The original rejection still propagates after the ping is sent.

Network errors during the ping never break the wrapped function — they're logged via `console.warn`.

## Programmatic management (API key required)

Get a key from your dashboard at **Account → API keys**. Then:

```ts
import { Whycron } from "whycron";

const wc = new Whycron({ apiKey: "wcr_live_..." });

const monitor = await wc.createMonitor({
  name: "Nightly Backup",
  scheduleType: "cron",
  scheduleValue: "0 2 * * *",
  gracePeriodSeconds: 120,
});

const monitors = await wc.listMonitors({ status: "failing" });
await wc.updateMonitor(monitor.id, { paused: true });
await wc.deleteMonitor(monitor.id);

const runs = await wc.listRuns({ monitorId: monitor.id });
const run = await wc.getRun(runs.items[0].id);
```

Scope-gated routes obey your key's scopes:

| Method | Scope needed |
|---|---|
| `listMonitors`, `getMonitor` | `monitors:read` |
| `createMonitor`, `updateMonitor`, `deleteMonitor` | `monitors:write` |
| `listRuns`, `getRun` | `runs:read` |

A `WhycronAuthError` (401) means the key is missing, malformed, or revoked. A `WhycronAPIError` with `statusCode === 403` means the key is valid but lacks the scope.

## Errors

| Exception | When |
|---|---|
| `WhycronAuthError` | 401 — bad/missing/revoked key |
| `WhycronNotFoundError` | 404 — wrong ID, or resource in another org |
| `WhycronRateLimitedError` | 429 — slow down |
| `WhycronAPIError` | any other non-2xx |
| `WhycronError` | base class of all of the above |

## Self-hosted / staging

```ts
const wc = new Whycron({
  apiKey: "...",
  baseUrl: "https://api.staging.example.com",
});
```

## License

MIT.
