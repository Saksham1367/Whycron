/**
 * Tiny helpers for rendering schedule values consistently across the
 * dashboard. The backend stores ``schedule_type`` + ``schedule_value``
 * separately; the UI usually wants a single human string.
 */

export type ScheduleType = "cron" | "interval" | "on_demand";

export function formatSchedule(
  scheduleType: ScheduleType,
  scheduleValue: string,
): string {
  if (scheduleType === "cron") return scheduleValue;
  if (scheduleType === "on_demand") return "On-demand";
  // interval — seconds string in scheduleValue
  const seconds = Number.parseInt(scheduleValue, 10);
  if (!Number.isFinite(seconds) || seconds < 1) return "Invalid interval";
  if (seconds < 60) return `Every ${seconds}s`;
  if (seconds < 3600) {
    const m = Math.round(seconds / 60);
    return `Every ${m} min`;
  }
  if (seconds < 86400) {
    const h = Math.round(seconds / 3600);
    return `Every ${h}h`;
  }
  const d = Math.round(seconds / 86400);
  return `Every ${d}d`;
}
