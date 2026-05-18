/**
 * Live preview of the next ~5 fire times for a cron / interval schedule,
 * plus a human-readable description ("At 02:00 AM"). Recomputes on every
 * keystroke. All parsing is client-side so the field gives instant
 * feedback without an API round-trip.
 */
import { useMemo } from "react";
import CronExpressionParser from "cron-parser";
import cronstrue from "cronstrue";
import { SymbolIcon } from "@/components/SymbolIcon";

type ScheduleType = "cron" | "interval" | "on_demand";

interface Props {
  scheduleType: ScheduleType;
  scheduleValue: string;
  timezone: string;
  count?: number;
}

interface Computed {
  description: string;
  fires: Date[];
}

function computePreview(
  scheduleType: ScheduleType,
  scheduleValue: string,
  timezone: string,
  count: number,
): Computed | { error: string } {
  const trimmed = scheduleValue.trim();

  if (scheduleType === "on_demand") {
    return {
      description: "Triggered manually — no scheduled fire times.",
      fires: [],
    };
  }

  if (!trimmed) {
    return { error: "Enter a schedule to see the preview." };
  }

  if (scheduleType === "interval") {
    const seconds = Number.parseInt(trimmed, 10);
    if (!Number.isFinite(seconds) || seconds < 1) {
      return {
        error:
          "Interval must be an integer number of seconds (e.g. 300 for every 5 minutes).",
      };
    }
    return {
      description: humanInterval(seconds),
      fires: nextIntervalFires(seconds, count),
    };
  }

  // cron
  try {
    const interval = CronExpressionParser.parse(trimmed, {
      tz: timezone || "UTC",
    });
    const fires: Date[] = [];
    for (let i = 0; i < count; i += 1) {
      fires.push(interval.next().toDate());
    }
    let description: string;
    try {
      description = cronstrue.toString(trimmed, { verbose: false });
    } catch {
      description = "Custom cron expression";
    }
    return { description, fires };
  } catch (e) {
    return {
      error:
        e instanceof Error
          ? e.message.replace(/^Error:\s*/, "")
          : "Invalid cron expression.",
    };
  }
}

function humanInterval(seconds: number): string {
  if (seconds < 60) return `Every ${seconds} second${seconds === 1 ? "" : "s"}`;
  if (seconds < 3600) {
    const m = Math.round(seconds / 60);
    return `Every ${m} minute${m === 1 ? "" : "s"}`;
  }
  if (seconds < 86400) {
    const h = Math.round(seconds / 3600);
    return `Every ${h} hour${h === 1 ? "" : "s"}`;
  }
  const d = Math.round(seconds / 86400);
  return `Every ${d} day${d === 1 ? "" : "s"}`;
}

function nextIntervalFires(seconds: number, count: number): Date[] {
  const now = Date.now();
  const out: Date[] = [];
  for (let i = 1; i <= count; i += 1) {
    out.push(new Date(now + i * seconds * 1000));
  }
  return out;
}

function relative(date: Date, now: number): string {
  const diff = date.getTime() - now;
  if (diff <= 0) return "now";
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `in ${sec}s`;
  const min = Math.round(sec / 60);
  if (min < 60) return `in ${min} min`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `in ${hr}h`;
  const days = Math.round(hr / 24);
  return `in ${days}d`;
}

export function CronPreview({
  scheduleType,
  scheduleValue,
  timezone,
  count = 5,
}: Props) {
  const result = useMemo(
    () => computePreview(scheduleType, scheduleValue, timezone, count),
    [scheduleType, scheduleValue, timezone, count],
  );

  const now = Date.now();

  if ("error" in result) {
    return (
      <div className="wc-cron-preview wc-cron-preview--error">
        <div className="wc-cron-preview__head">
          <SymbolIcon name="error" size="1.05rem" color="var(--wc-danger)" />
          <strong>Schedule won't validate</strong>
        </div>
        <p>{result.error}</p>
      </div>
    );
  }

  return (
    <div className="wc-cron-preview">
      <div className="wc-cron-preview__head">
        <SymbolIcon
          name="schedule_send"
          size="1.05rem"
          color="var(--wc-primary-strong)"
        />
        <strong>{result.description}</strong>
      </div>
      {result.fires.length > 0 && (
        <>
          <p className="wc-cron-preview__sublabel">
            Next {result.fires.length} fire times
            {scheduleType === "cron" ? ` (${timezone || "UTC"})` : ""}:
          </p>
          <ol className="wc-cron-preview__list">
            {result.fires.map((d, i) => (
              <li key={i}>
                <span className="wc-cron-preview__when">
                  {d.toLocaleString(undefined, {
                    weekday: "short",
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <span className="wc-cron-preview__rel">
                  {relative(d, now)}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
