/**
 * Typed wrapper around `fetch` for the Whycron REST API.
 *
 * - Auto-attaches the current Supabase JWT as a Bearer token.
 * - Parses JSON responses, throws `ApiError` on non-2xx with the parsed body.
 * - Treats 204 as `null`.
 *
 * One module-level singleton; no caching layer (callers do their own state).
 */
import { config } from "./config";
import { supabase } from "./supabase";
import type {
  Account,
  ChannelListResponse,
  Monitor,
  MonitorDetail,
  MonitorListResponse,
  NotificationChannel,
  Run,
  RunListResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) return {};
  return { Authorization: `Bearer ${session.access_token}` };
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  const response = await fetch(`${config.apiUrl}${path}`, {
    ...init,
    headers,
  });

  if (response.status === 204) return null as T;

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(response.status, message, body);
  }
  return body as T;
}

// ── Auth ────────────────────────────────────────────────────────────────────

export interface MeResponse {
  user_id: string;
  organization_id: string;
  supabase_user_id: string;
  email: string;
  name: string | null;
  role: string;
}

export const api = {
  me: (): Promise<MeResponse> => request("/api/v1/auth/me"),

  // ── Monitors ─────────────────────────────────────────────────────────────
  listMonitors: (params: {
    status?: string;
    tag?: string;
    search?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<MonitorListResponse> => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.tag) q.set("tag", params.tag);
    if (params.search) q.set("search", params.search);
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request(`/api/v1/monitors${qs ? `?${qs}` : ""}`);
  },

  createMonitor: (body: {
    name: string;
    schedule_type: "cron" | "interval" | "on_demand";
    schedule_value: string;
    timezone?: string;
    grace_period_seconds?: number;
    expected_runtime_seconds?: number | null;
    tags?: string[];
    notification_settings?: Record<string, unknown>;
  }): Promise<Monitor> =>
    request("/api/v1/monitors", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getMonitor: (id: string): Promise<MonitorDetail> =>
    request(`/api/v1/monitors/${id}?runs_limit=20`),

  updateMonitor: (
    id: string,
    body: Partial<{
      name: string;
      schedule_type: string;
      schedule_value: string;
      timezone: string;
      grace_period_seconds: number;
      expected_runtime_seconds: number | null;
      paused: boolean;
      is_public: boolean;
      tags: string[];
    }>
  ): Promise<Monitor> =>
    request(`/api/v1/monitors/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteMonitor: (id: string): Promise<null> =>
    request(`/api/v1/monitors/${id}`, { method: "DELETE" }),

  // ── Runs ────────────────────────────────────────────────────────────────
  listRuns: (params: {
    monitor_id?: string;
    state?: string;
    since?: string;
    until?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<RunListResponse> => {
    const q = new URLSearchParams();
    if (params.monitor_id) q.set("monitor_id", params.monitor_id);
    if (params.state) q.set("state", params.state);
    if (params.since) q.set("since", params.since);
    if (params.until) q.set("until", params.until);
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request(`/api/v1/runs${qs ? `?${qs}` : ""}`);
  },

  getRun: (id: string): Promise<Run> => request(`/api/v1/runs/${id}`),

  postRunFeedback: (
    id: string,
    feedback: "helpful" | "not_helpful"
  ): Promise<null> =>
    request(`/api/v1/runs/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),

  // ── Notification channels ───────────────────────────────────────────────
  listChannels: (): Promise<ChannelListResponse> =>
    request("/api/v1/notification-channels"),

  createChannel: (body: {
    type: "email" | "webhook" | "slack" | "discord";
    name: string;
    config: Record<string, unknown>;
    enabled?: boolean;
  }): Promise<NotificationChannel> =>
    request("/api/v1/notification-channels", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateChannel: (
    id: string,
    body: Partial<{
      name: string;
      config: Record<string, unknown>;
      enabled: boolean;
    }>
  ): Promise<NotificationChannel> =>
    request(`/api/v1/notification-channels/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteChannel: (id: string): Promise<null> =>
    request(`/api/v1/notification-channels/${id}`, { method: "DELETE" }),

  // ── Account ─────────────────────────────────────────────────────────────
  getAccount: (): Promise<Account> => request("/api/v1/account"),

  // ── Billing ─────────────────────────────────────────────────────────────
  startCheckout: (tier: "pro" | "team" = "pro"): Promise<{ checkout_url: string }> =>
    request("/api/v1/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ tier }),
    }),

  openPortal: (): Promise<{ portal_url: string }> =>
    request("/api/v1/billing/portal"),

  // ── API keys ────────────────────────────────────────────────────────────
  listApiKeys: (): Promise<ApiKey[]> => request("/api/v1/api-keys"),

  createApiKey: (body: {
    name: string;
    scopes: ApiKeyScope[];
    expires_at?: string | null;
  }): Promise<ApiKeyCreated> =>
    request("/api/v1/api-keys", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  revokeApiKey: (id: string): Promise<null> =>
    request(`/api/v1/api-keys/${id}`, { method: "DELETE" }),

  // ── Slack integration ───────────────────────────────────────────────────
  getSlackInstallation: (): Promise<SlackInstallationInfo> =>
    request("/api/v1/integrations/slack"),

  startSlackInstall: (): Promise<{ authorize_url: string }> =>
    request("/api/v1/integrations/slack/install"),

  uninstallSlack: (): Promise<null> =>
    request("/api/v1/integrations/slack", { method: "DELETE" }),

  listSlackChannels: (): Promise<SlackChannelsResponse> =>
    request("/api/v1/integrations/slack/channels"),

  // ── Status page ─────────────────────────────────────────────────────────
  getStatusPageConfig: (): Promise<StatusPageConfig> =>
    request("/api/v1/status-page"),

  updateStatusPageConfig: (body: {
    slug?: string | null;
    headline?: string | null;
  }): Promise<StatusPageConfig> =>
    request("/api/v1/status-page", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export type ApiKeyScope =
  | "monitors:read"
  | "monitors:write"
  | "runs:read"
  | "admin";

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: ApiKeyScope[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  plaintext: string;
}

export interface SlackInstallationInfo {
  connected: boolean;
  team_id?: string;
  team_name?: string;
  scopes?: string[];
  installed_at?: string;
}

export interface SlackChannelOption {
  id: string;
  name: string;
  is_private: boolean;
  is_member: boolean;
}

export interface SlackChannelsResponse {
  team_name: string;
  channels: SlackChannelOption[];
}

export interface StatusPageConfig {
  slug: string | null;
  headline: string | null;
  public_monitor_count: number;
  total_monitor_count: number;
  public_url: string | null;
}
