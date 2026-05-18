# whycron — Python client for Whycron

Cron job monitoring that tells you why. This is the official Python SDK.

```bash
pip install whycron
```

## Heartbeat pings

The ping token is the credential — no API key needed.

```python
from whycron import Whycron

client = Whycron()

client.ping("wcr_abc123def", state="started")
try:
    do_the_work()
    client.ping("wcr_abc123def", state="succeeded", duration_ms=1234)
except Exception as exc:
    client.ping("wcr_abc123def", state="failed", exit_code=1, logs=str(exc))
    raise
```

## Decorator

For most jobs, this is all you need:

```python
import whycron

@whycron.monitor("wcr_abc123def")
def nightly_backup():
    ...
```

Sends a `started` ping before the function runs, then `succeeded` (with `exit_code=0` and `duration_ms`) on a clean return, or `failed` (with `exit_code=1`, `duration_ms`, and the traceback tail as `logs`) if it raises. The exception still propagates after the ping is sent.

Network errors during the ping never break the wrapped function — they're logged via the standard library `logging` module under the `whycron` logger.

## Programmatic management (API key required)

Get a key from your dashboard at **Account → API keys**. Then:

```python
from whycron import Whycron

client = Whycron(api_key="wcr_live_...")

monitor = client.create_monitor(
    name="Nightly Backup",
    schedule_type="cron",
    schedule_value="0 2 * * *",
    grace_period_seconds=120,
)

monitors = client.list_monitors(status="failing")
client.update_monitor(monitor["id"], paused=True)
client.delete_monitor(monitor["id"])

runs = client.list_runs(monitor_id=monitor["id"])
run = client.get_run(runs["items"][0]["id"])
```

Scope-gated routes obey your key's scopes:

| Method | Scope needed |
|---|---|
| `list_monitors`, `get_monitor` | `monitors:read` |
| `create_monitor`, `update_monitor`, `delete_monitor` | `monitors:write` |
| `list_runs`, `get_run` | `runs:read` |

A `WhycronAuthError` (401) means the key is missing, malformed, or revoked. A `WhycronAPIError` with `.status_code == 403` means the key is valid but lacks the scope.

## Errors

| Exception | When |
|---|---|
| `WhycronAuthError` | 401 — bad/missing/revoked key |
| `WhycronNotFoundError` | 404 — wrong ID, or resource in another org |
| `WhycronRateLimitedError` | 429 — slow down |
| `WhycronAPIError` | any other non-2xx |
| `WhycronError` | base class of all of the above |

## Self-hosted / staging

```python
client = Whycron(api_key="...", base_url="https://api.staging.example.com")
```

## License

MIT.
