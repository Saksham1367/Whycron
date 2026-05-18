/**
 * Whycron HTTP client — uses native fetch (Node 18+).
 */

import {
  WhycronAPIError,
  WhycronAuthError,
  WhycronNotFoundError,
  WhycronRateLimitedError,
} from "./errors.js";
import type {
  CreateMonitorOptions,
  ListMonitorsOptions,
  ListRunsOptions,
  PingOptions,
  PingResponse,
  UpdateMonitorOptions,
  WhycronClientOptions,
} from "./types.js";

const DEFAULT_BASE_URL = "https://api.whycron.com";
const DEFAULT_TIMEOUT_MS = 10_000;
const USER_AGENT = "whycron-node/0.1.0";

export class Whycron {
  private readonly apiKey: string | undefined;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: WhycronClientOptions = {}) {
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.fetchImpl = options.fetch ?? fetch;
  }

  /**
   * Heartbeat ping. No API key required — the ping token IS the credential.
   */
  async ping(
    pingToken: string,
    options: PingOptions = {},
  ): Promise<PingResponse> {
    const state = options.state ?? "succeeded";
    const parts = [`/p/${pingToken}`];
    if (state !== "succeeded") {
      parts.push(state);
    }
    if (options.externalId) {
      if (state === "succeeded") parts.push("succeeded");
      parts.push(options.externalId);
    }
    const path = parts.join("/");

    const payload: Record<string, unknown> = {};
    if (options.exitCode !== undefined) payload.exit_code = options.exitCode;
    if (options.durationMs !== undefined) payload.duration_ms = options.durationMs;
    if (options.logs !== undefined) payload.logs = options.logs;
    if (options.metadata !== undefined) payload.metadata = options.metadata;

    return this.request<PingResponse>("POST", path, {
      body: Object.keys(payload).length > 0 ? payload : undefined,
      authed: false,
    });
  }

  // ── monitors ────────────────────────────────────────────────────────────

  async listMonitors(options: ListMonitorsOptions = {}): Promise<unknown> {
    return this.request("GET", "/api/v1/monitors", {
      query: {
        limit: options.limit ?? 50,
        offset: options.offset ?? 0,
        status: options.status,
        tag: options.tag,
        search: options.search,
      },
      authed: true,
    });
  }

  async createMonitor(options: CreateMonitorOptions): Promise<unknown> {
    const body: Record<string, unknown> = {
      name: options.name,
      schedule_type: options.scheduleType,
      schedule_value: options.scheduleValue,
      timezone: options.timezone ?? "UTC",
      grace_period_seconds: options.gracePeriodSeconds ?? 60,
    };
    if (options.expectedRuntimeSeconds !== undefined) {
      body.expected_runtime_seconds = options.expectedRuntimeSeconds;
    }
    if (options.tags !== undefined) body.tags = options.tags;
    if (options.notificationSettings !== undefined) {
      body.notification_settings = options.notificationSettings;
    }
    return this.request("POST", "/api/v1/monitors", { body, authed: true });
  }

  async getMonitor(monitorId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/monitors/${monitorId}`, {
      authed: true,
    });
  }

  async updateMonitor(
    monitorId: string,
    fields: UpdateMonitorOptions,
  ): Promise<unknown> {
    if (Object.keys(fields).length === 0) {
      throw new Error(
        "updateMonitor requires at least one field to change",
      );
    }
    const body: Record<string, unknown> = {};
    if (fields.name !== undefined) body.name = fields.name;
    if (fields.scheduleType !== undefined) body.schedule_type = fields.scheduleType;
    if (fields.scheduleValue !== undefined) body.schedule_value = fields.scheduleValue;
    if (fields.timezone !== undefined) body.timezone = fields.timezone;
    if (fields.gracePeriodSeconds !== undefined) body.grace_period_seconds = fields.gracePeriodSeconds;
    if (fields.expectedRuntimeSeconds !== undefined) body.expected_runtime_seconds = fields.expectedRuntimeSeconds;
    if (fields.paused !== undefined) body.paused = fields.paused;
    if (fields.tags !== undefined) body.tags = fields.tags;

    return this.request("PATCH", `/api/v1/monitors/${monitorId}`, {
      body,
      authed: true,
    });
  }

  async deleteMonitor(monitorId: string): Promise<void> {
    await this.request("DELETE", `/api/v1/monitors/${monitorId}`, {
      authed: true,
    });
  }

  // ── runs ────────────────────────────────────────────────────────────────

  async listRuns(options: ListRunsOptions = {}): Promise<unknown> {
    return this.request("GET", "/api/v1/runs", {
      query: {
        limit: options.limit ?? 50,
        offset: options.offset ?? 0,
        monitor_id: options.monitorId,
        state: options.state,
        since: options.since,
        until: options.until,
      },
      authed: true,
    });
  }

  async getRun(runId: string): Promise<unknown> {
    return this.request("GET", `/api/v1/runs/${runId}`, { authed: true });
  }

  // ── internals ───────────────────────────────────────────────────────────

  private async request<T = unknown>(
    method: string,
    path: string,
    options: {
      query?: Record<string, unknown> | undefined;
      body?: Record<string, unknown> | undefined;
      authed: boolean;
    },
  ): Promise<T> {
    if (options.authed && !this.apiKey) {
      throw new WhycronAPIError(
        0,
        "apiKey is required for this method. Pass it to new Whycron({ apiKey: ... }).",
      );
    }

    const url = new URL(this.baseUrl + path);
    if (options.query) {
      for (const [key, value] of Object.entries(options.query)) {
        if (value === undefined || value === null) continue;
        url.searchParams.set(key, String(value));
      }
    }

    const headers: Record<string, string> = {
      "User-Agent": USER_AGENT,
      Accept: "application/json",
    };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    if (options.authed && this.apiKey) {
      headers["X-Whycron-API-Key"] = this.apiKey;
    }

    const controller = new AbortController();
    const timeoutHandle = setTimeout(() => controller.abort(), this.timeoutMs);

    let response: Response;
    try {
      response = await this.fetchImpl(url.toString(), {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutHandle);
    }

    return (await this.unwrap(response)) as T;
  }

  private async unwrap(response: Response): Promise<unknown> {
    if (response.status === 204) return {};

    const text = await response.text();
    let parsed: unknown = undefined;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = text;
      }
    }

    if (response.ok) {
      return parsed ?? {};
    }

    const detail =
      parsed !== null &&
      typeof parsed === "object" &&
      "detail" in (parsed as Record<string, unknown>)
        ? String((parsed as Record<string, unknown>).detail)
        : undefined;
    const message = detail ?? response.statusText ?? "Whycron request failed";

    switch (response.status) {
      case 401:
        throw new WhycronAuthError(401, message, parsed);
      case 404:
        throw new WhycronNotFoundError(404, message, parsed);
      case 429:
        throw new WhycronRateLimitedError(429, message, parsed);
      default:
        throw new WhycronAPIError(response.status, message, parsed);
    }
  }
}
