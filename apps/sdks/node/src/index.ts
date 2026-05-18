export { Whycron } from "./client.js";
export { withMonitor } from "./with-monitor.js";
export type { WithMonitorOptions } from "./with-monitor.js";
export {
  WhycronAPIError,
  WhycronAuthError,
  WhycronError,
  WhycronNotFoundError,
  WhycronRateLimitedError,
} from "./errors.js";
export type {
  CreateMonitorOptions,
  ListMonitorsOptions,
  ListRunsOptions,
  PingOptions,
  PingResponse,
  PingState,
  ScheduleType,
  UpdateMonitorOptions,
  WhycronClientOptions,
} from "./types.js";

export const VERSION = "0.1.0";
