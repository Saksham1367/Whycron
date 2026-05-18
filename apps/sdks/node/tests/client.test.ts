/**
 * Whycron Node SDK — unit tests. Mocks ``fetch`` via dependency injection.
 */

import { describe, expect, it, vi } from "vitest";
import {
  Whycron,
  WhycronAPIError,
  WhycronAuthError,
  WhycronNotFoundError,
  WhycronRateLimitedError,
  withMonitor,
} from "../src/index.js";

const BASE = "https://api.whycron.com";
const TOKEN = "wcr_abc123def456";
const API_KEY = "wcr_live_testtest";

// ── helpers ───────────────────────────────────────────────────────────────

interface RecordedCall {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | undefined;
}

function makeFetch(
  responses: { status: number; json?: unknown; text?: string }[],
): { fetchImpl: typeof fetch; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  let i = 0;
  const fetchImpl: typeof fetch = (async (
    url: RequestInfo | URL,
    init: RequestInit = {},
  ) => {
    const headers: Record<string, string> = {};
    if (init.headers) {
      for (const [k, v] of Object.entries(
        init.headers as Record<string, string>,
      )) {
        headers[k.toLowerCase()] = v;
      }
    }
    calls.push({
      url: url.toString(),
      method: init.method ?? "GET",
      headers,
      body:
        typeof init.body === "string"
          ? init.body
          : init.body === undefined
            ? undefined
            : String(init.body),
    });
    const spec = responses[i++];
    if (!spec) throw new Error("makeFetch ran out of canned responses");
    const text = spec.json !== undefined ? JSON.stringify(spec.json) : (spec.text ?? "");
    // The Fetch spec forbids a body on 204/205/304 — pass null in those cases.
    const noBodyStatuses = new Set([204, 205, 304]);
    const body = noBodyStatuses.has(spec.status) ? null : text;
    return new Response(body, {
      status: spec.status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return { fetchImpl, calls };
}

// ── ping ──────────────────────────────────────────────────────────────────

describe("ping", () => {
  it("hits the bare token path for a default (succeeded) ping", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { status: "ok", run_id: "r1" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    const result = await wc.ping(TOKEN);
    expect(result).toEqual({ status: "ok", run_id: "r1" });
    expect(calls[0]?.url).toBe(`${BASE}/p/${TOKEN}`);
    expect(calls[0]?.method).toBe("POST");
    // No body when there are no fields.
    expect(calls[0]?.body).toBeUndefined();
  });

  it("appends state to path for failed and serializes fields", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { status: "ok", run_id: "r1" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    await wc.ping(TOKEN, {
      state: "failed",
      exitCode: 1,
      durationMs: 1234,
      logs: "boom",
    });
    expect(calls[0]?.url).toBe(`${BASE}/p/${TOKEN}/failed`);
    expect(JSON.parse(calls[0]!.body!)).toEqual({
      exit_code: 1,
      duration_ms: 1234,
      logs: "boom",
    });
  });

  it("uses the started path", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { status: "ok", run_id: "r1" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    await wc.ping(TOKEN, { state: "started" });
    expect(calls[0]?.url).toBe(`${BASE}/p/${TOKEN}/started`);
  });

  it("includes the state segment when an externalId is given", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { status: "ok", run_id: "r1" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    await wc.ping(TOKEN, { state: "succeeded", externalId: "job-42" });
    expect(calls[0]?.url).toBe(`${BASE}/p/${TOKEN}/succeeded/job-42`);
  });

  it("serializes metadata", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { status: "ok", run_id: "r1" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    await wc.ping(TOKEN, { metadata: { env: "prod" } });
    expect(JSON.parse(calls[0]!.body!)).toEqual({ metadata: { env: "prod" } });
  });
});

// ── monitor CRUD ──────────────────────────────────────────────────────────

describe("monitors", () => {
  it("sends the X-Whycron-API-Key header on create", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 201, json: { id: "m1", name: "Backup" } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    const result = await wc.createMonitor({
      name: "Backup",
      scheduleType: "cron",
      scheduleValue: "0 2 * * *",
    });
    expect((result as { id: string }).id).toBe("m1");
    expect(calls[0]?.headers["x-whycron-api-key"]).toBe(API_KEY);
    const body = JSON.parse(calls[0]!.body!);
    expect(body.name).toBe("Backup");
    expect(body.schedule_type).toBe("cron");
    expect(body.schedule_value).toBe("0 2 * * *");
    expect(body.timezone).toBe("UTC");
    expect(body.grace_period_seconds).toBe(60);
  });

  it("lists with filters", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { items: [] } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    await wc.listMonitors({ status: "failing", limit: 10 });
    expect(calls[0]?.url).toContain("limit=10");
    expect(calls[0]?.url).toContain("status=failing");
  });

  it("getMonitor", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { id: "m1", name: "Backup" } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    const result = await wc.getMonitor("m1");
    expect(calls[0]?.url).toBe(`${BASE}/api/v1/monitors/m1`);
    expect((result as { name: string }).name).toBe("Backup");
  });

  it("updateMonitor rejects an empty patch", async () => {
    const wc = new Whycron({ apiKey: API_KEY });
    await expect(wc.updateMonitor("m1", {})).rejects.toThrow(/at least one/);
  });

  it("updateMonitor sends only the provided fields", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { id: "m1" } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    await wc.updateMonitor("m1", { name: "Renamed", paused: true });
    expect(calls[0]?.method).toBe("PATCH");
    expect(JSON.parse(calls[0]!.body!)).toEqual({
      name: "Renamed",
      paused: true,
    });
  });

  it("deleteMonitor handles 204", async () => {
    const { fetchImpl } = makeFetch([{ status: 204, text: "" }]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    await wc.deleteMonitor("m1");
  });
});

// ── runs ──────────────────────────────────────────────────────────────────

describe("runs", () => {
  it("listRuns includes monitorId filter", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { items: [] } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    await wc.listRuns({ monitorId: "m1" });
    expect(calls[0]?.url).toContain("monitor_id=m1");
  });

  it("getRun", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { id: "r1", state: "succeeded" } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    const result = await wc.getRun("r1");
    expect(calls[0]?.url).toBe(`${BASE}/api/v1/runs/r1`);
    expect((result as { state: string }).state).toBe("succeeded");
  });
});

// ── auth/error handling ──────────────────────────────────────────────────

describe("errors", () => {
  it("throws when an authed method is called without an apiKey", async () => {
    const wc = new Whycron();
    await expect(wc.listMonitors()).rejects.toBeInstanceOf(WhycronAPIError);
  });

  it("maps 401 to WhycronAuthError", async () => {
    const { fetchImpl } = makeFetch([
      { status: 401, json: { detail: "Invalid or revoked API key" } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    await expect(wc.listMonitors()).rejects.toBeInstanceOf(WhycronAuthError);
  });

  it("maps 404 to WhycronNotFoundError", async () => {
    const { fetchImpl } = makeFetch([
      { status: 404, json: { detail: "Monitor not found" } },
    ]);
    const wc = new Whycron({ apiKey: API_KEY, fetch: fetchImpl });
    await expect(wc.getMonitor("nope")).rejects.toBeInstanceOf(
      WhycronNotFoundError,
    );
  });

  it("maps 429 to WhycronRateLimitedError", async () => {
    const { fetchImpl } = makeFetch([
      { status: 429, json: { detail: "Slow down" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    await expect(wc.ping(TOKEN)).rejects.toBeInstanceOf(
      WhycronRateLimitedError,
    );
  });
});

// ── withMonitor ──────────────────────────────────────────────────────────

describe("withMonitor", () => {
  it("pings started and succeeded around a clean async run", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { status: "ok" } },
      { status: 200, json: { status: "ok" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    const wrapped = withMonitor(TOKEN, wc, async () => 42);
    const result = await wrapped();
    expect(result).toBe(42);
    expect(calls[0]?.url).toBe(`${BASE}/p/${TOKEN}/started`);
    expect(calls[1]?.url).toBe(`${BASE}/p/${TOKEN}`);
    const succeededBody = JSON.parse(calls[1]!.body!);
    expect(succeededBody.exit_code).toBe(0);
    expect(typeof succeededBody.duration_ms).toBe("number");
  });

  it("pings failed when the async function rejects, then rethrows", async () => {
    const { fetchImpl, calls } = makeFetch([
      { status: 200, json: { status: "ok" } },
      { status: 200, json: { status: "ok" } },
    ]);
    const wc = new Whycron({ fetch: fetchImpl });
    const wrapped = withMonitor(TOKEN, wc, async () => {
      throw new Error("kaboom");
    });
    await expect(wrapped()).rejects.toThrow("kaboom");
    expect(calls[1]?.url).toBe(`${BASE}/p/${TOKEN}/failed`);
    const failedBody = JSON.parse(calls[1]!.body!);
    expect(failedBody.exit_code).toBe(1);
    expect(failedBody.logs).toContain("kaboom");
  });

  it("does not propagate a ping failure into the wrapped function", async () => {
    const { fetchImpl } = makeFetch([
      // started ping fails
      { status: 500, json: { detail: "boom" } },
      // succeeded ping
      { status: 200, json: { status: "ok" } },
    ]);
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const wc = new Whycron({ fetch: fetchImpl });
    const wrapped = withMonitor(TOKEN, wc, async () => "ran-anyway");
    const result = await wrapped();
    expect(result).toBe("ran-anyway");
    consoleWarn.mockRestore();
  });
});
