/**
 * Shared types for the Whycron Node SDK.
 */

export type PingState = "succeeded" | "failed" | "started";
export type ScheduleType = "cron" | "interval" | "on_demand";

export interface PingOptions {
  state?: PingState;
  exitCode?: number;
  durationMs?: number;
  logs?: string;
  externalId?: string;
  metadata?: Record<string, unknown>;
}

export interface PingResponse {
  status: string;
  run_id: string;
}

export interface CreateMonitorOptions {
  name: string;
  scheduleType: ScheduleType;
  scheduleValue: string;
  timezone?: string;
  gracePeriodSeconds?: number;
  expectedRuntimeSeconds?: number;
  tags?: string[];
  notificationSettings?: Record<string, unknown>;
}

export interface UpdateMonitorOptions {
  name?: string;
  scheduleType?: ScheduleType;
  scheduleValue?: string;
  timezone?: string;
  gracePeriodSeconds?: number;
  expectedRuntimeSeconds?: number | null;
  paused?: boolean;
  tags?: string[];
}

export interface ListMonitorsOptions {
  status?: string;
  tag?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface ListRunsOptions {
  monitorId?: string;
  state?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export interface WhycronClientOptions {
  apiKey?: string;
  baseUrl?: string;
  timeoutMs?: number;
  fetch?: typeof fetch;
}
