import type { MonitorStatus, RunState } from "@/lib/types";

interface Props {
  status: MonitorStatus | RunState | string;
}

const LABELS: Record<string, string> = {
  healthy: "Healthy",
  late: "Late",
  failing: "Failing",
  paused: "Paused",
  unknown: "Unknown",
  succeeded: "Succeeded",
  failed: "Failed",
  missed: "Missed",
  started: "Started",
  timed_out: "Timed out",
};

const TONES: Record<string, string> = {
  healthy: "healthy",
  succeeded: "healthy",
  late: "late",
  failing: "failing",
  failed: "failing",
  missed: "failing",
  timed_out: "failing",
  paused: "paused",
  unknown: "paused",
  started: "paused",
};

export function StatusBadge({ status }: Props) {
  const tone = TONES[status] ?? "paused";
  const label = LABELS[status] ?? status;
  return (
    <span className={`wc-badge wc-badge--${tone}`}>
      <span className="wc-dot" />
      {label}
    </span>
  );
}
