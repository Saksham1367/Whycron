/**
 * TypeScript interfaces mirroring the Whycron API response shapes from
 * `apps/api/schemas/`. Keep these in sync; the backend is the contract.
 */

export type MonitorStatus =
  | "healthy"
  | "failing"
  | "late"
  | "paused"
  | "unknown";

export type RunState =
  | "started"
  | "succeeded"
  | "failed"
  | "missed"
  | "late"
  | "timed_out";

export interface Monitor {
  id: string;
  name: string;
  ping_token: string;
  schedule_type: "cron" | "interval" | "on_demand";
  schedule_value: string;
  timezone: string;
  grace_period_seconds: number;
  expected_runtime_seconds: number | null;
  status: MonitorStatus;
  paused: boolean;
  tags: string[];
  notification_settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MonitorRecentRun {
  id: string;
  state: RunState;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  exit_code: number | null;
  created_at: string;
}

export interface MonitorDetail {
  monitor: Monitor;
  recent_runs: MonitorRecentRun[];
}

export interface MonitorListResponse {
  items: Monitor[];
  total: number;
  limit: number;
  offset: number;
}

export interface AIExplanation {
  id: string;
  prompt_version: string;
  model: string;
  root_cause: string;
  explanation: string;
  suggested_fix: string | null;
  confidence: "low" | "medium" | "high";
  input_tokens: number;
  output_tokens: number;
  cost_usd_micro: number;
  user_feedback: "helpful" | "not_helpful" | null;
  cached_from_signature_hash: string | null;
  created_at: string;
}

export interface Run {
  id: string;
  monitor_id: string;
  state: RunState;
  run_external_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  exit_code: number | null;
  log_excerpt: string | null;
  log_size_bytes: number | null;
  failure_signature_hash: string | null;
  created_at: string;
  explanation?: AIExplanation | null;
}

export interface RunListResponse {
  items: Run[];
  total: number;
  limit: number;
  offset: number;
}

export type ChannelType = "email" | "webhook" | "slack" | "discord";

export interface NotificationChannel {
  id: string;
  type: ChannelType;
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChannelListResponse {
  items: NotificationChannel[];
  total: number;
  limit: number;
  offset: number;
}

export interface AccountUsage {
  monitors_active: number;
  monitors_limit: number; // -1 = unlimited
  ai_explanations_this_month: number;
  ai_explanations_monthly_limit: number; // -1 = unlimited
}

export interface Account {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  tier: string;
  features: Record<string, unknown>;
  user_id: string;
  email: string;
  name: string | null;
  role: string;
  usage: AccountUsage;
  created_at: string;
}
