import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { Eyebrow } from "@/components/Eyebrow";
import { StatusBadge } from "@/components/StatusBadge";
import { SurfaceCard } from "@/components/SurfaceCard";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { api } from "@/lib/api";
import { fmtDuration, fmtRelative } from "@/lib/format";
import type { Monitor, Run } from "@/lib/types";

const FAILURE_STATES = [
  { id: "", label: "All non-success" },
  { id: "failed", label: "Failed" },
  { id: "missed", label: "Missed" },
  { id: "timed_out", label: "Timed out" },
  { id: "late", label: "Late" },
];

export function FailuresScreen() {
  const { onSignOut } = useOutletContext<ShellContext>();
  const [searchParams] = useSearchParams();
  const monitorIdFilter = searchParams.get("monitor_id") ?? undefined;

  const [runs, setRuns] = useState<Run[] | null>(null);
  const [monitorsById, setMonitorsById] = useState<Record<string, Monitor>>({});
  const [state, setState] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setRuns(null);
    Promise.all([
      api.listRuns({
        monitor_id: monitorIdFilter,
        state: state || undefined,
        limit: 100,
      }),
      api.listMonitors({ limit: 200 }),
    ])
      .then(([rRuns, rMon]) => {
        if (!mounted) return;
        // Restrict to non-succeeded states if no filter was supplied.
        const filtered = state
          ? rRuns.items
          : rRuns.items.filter((r) => r.state !== "succeeded" && r.state !== "started");
        setRuns(filtered);
        setMonitorsById(
          Object.fromEntries(rMon.items.map((m) => [m.id, m]))
        );
      })
      .catch((e: Error) => mounted && setError(e.message));
    return () => {
      mounted = false;
    };
  }, [state, monitorIdFilter]);

  return (
    <>
      <Topbar
        crumbs={[{ label: "Failures", last: true }]}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>Activity</Eyebrow>
          <h1 className="wc-page-title">Failures</h1>
          <p className="wc-page-sub">
            Runs that failed, missed their schedule, or timed out — newest first.
          </p>
        </div>
      </div>

      <div className="wc-cluster" style={{ marginBottom: "1rem" }}>
        {FAILURE_STATES.map((f) => (
          <button
            key={f.id}
            className={`wc-pill ${state === f.id ? "wc-pill--active" : ""}`}
            onClick={() => setState(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <div className="wc-notice">{error}</div>}

      {runs == null ? (
        <SurfaceCard>
          <p style={{ color: "var(--wc-text-muted)" }}>Loading…</p>
        </SurfaceCard>
      ) : runs.length === 0 ? (
        <EmptyState
          icon="check_circle"
          title="Nothing to investigate"
          description="No failed, missed, or timed-out runs match this filter."
        />
      ) : (
        <SurfaceCard>
          {runs.map((r) => (
            <Link
              key={r.id}
              to={`/runs/${r.id}`}
              className="wc-activity"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <StatusBadge status={r.state} />
              <span className="wc-activity__monitor">
                {monitorsById[r.monitor_id]?.name ?? "Unknown monitor"}
              </span>
              <span className="wc-activity__time">
                {fmtRelative(r.ended_at ?? r.started_at ?? r.created_at)}
              </span>
              <span className="wc-activity__dur">
                {fmtDuration(r.duration_ms)}
              </span>
            </Link>
          ))}
        </SurfaceCard>
      )}
    </>
  );
}
