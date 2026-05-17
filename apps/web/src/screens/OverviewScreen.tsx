import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { Eyebrow } from "@/components/Eyebrow";
import { MetricCard } from "@/components/MetricCard";
import type { Metric } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { SurfaceCard } from "@/components/SurfaceCard";
import { SymbolIcon } from "@/components/SymbolIcon";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { api } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import type { Monitor, Run } from "@/lib/types";

export function OverviewScreen() {
  const { account, onSignOut } = useOutletContext<ShellContext>();
  const [monitors, setMonitors] = useState<Monitor[] | null>(null);
  const [recentFailures, setRecentFailures] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([
      api.listMonitors({ limit: 200 }),
      api.listRuns({ state: "failed", limit: 5 }),
    ])
      .then(([m, r]) => {
        if (!mounted) return;
        setMonitors(m.items);
        setRecentFailures(r.items);
      })
      .catch((e: Error) => {
        if (mounted) setError(e.message);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const counts = countByStatus(monitors);
  const metrics: Metric[] = [
    {
      label: "Healthy",
      value: counts.healthy,
      icon: "check_circle",
      tone: "healthy",
      help: `${monitors?.length ?? 0} total monitors`,
    },
    {
      label: "Failing",
      value: counts.failing,
      icon: "error",
      tone: "failing",
      help: counts.failing > 0 ? "Needs attention" : "All green",
    },
    {
      label: "Late",
      value: counts.late,
      icon: "schedule",
      tone: "late",
      help: "Grace period exceeded",
    },
    {
      label: "Paused",
      value: counts.paused,
      icon: "pause_circle",
      tone: "paused",
      help: "Not currently monitored",
    },
  ];

  return (
    <>
      <Topbar
        crumbs={[{ label: "Overview", last: true }]}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>{account?.tier?.toUpperCase() ?? "FREE"} TIER</Eyebrow>
          <h1 className="wc-page-title">
            Hello{account?.name ? `, ${account.name}` : ""}.
          </h1>
          <p className="wc-page-sub">
            {monitors == null
              ? "Loading workspace…"
              : monitors.length === 0
                ? "Create your first monitor to start receiving heartbeats."
                : "Live status of your scheduled jobs."}
          </p>
        </div>
        <Link
          to="/monitors/new"
          className="wc-btn wc-btn--primary"
          style={{ textDecoration: "none" }}
        >
          <SymbolIcon name="add" size="1.05rem" /> New monitor
        </Link>
      </div>

      {error && (
        <div className="wc-notice" style={{ marginBottom: "1.2rem" }}>
          <strong>Couldn't load overview:</strong> {error}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "1rem",
          marginBottom: "1.4rem",
        }}
      >
        {metrics.map((m) => (
          <MetricCard key={m.label} metric={m} />
        ))}
      </div>

      <SurfaceCard>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <div>
            <Eyebrow>Recent failures</Eyebrow>
            <h2
              style={{
                font: "600 1.25rem var(--wc-font-body)",
                letterSpacing: "-0.03em",
                margin: ".3rem 0 0",
              }}
            >
              Last 5 failed runs
            </h2>
          </div>
          <Link
            to="/failures"
            style={{ color: "var(--wc-primary)", fontSize: ".85rem" }}
          >
            View all →
          </Link>
        </div>

        {recentFailures == null ? (
          <p style={{ color: "var(--wc-text-muted)" }}>Loading…</p>
        ) : recentFailures.length === 0 ? (
          <EmptyState
            icon="check_circle"
            title="No recent failures"
            description="Whycron will show failed runs here as they happen. Run a ping to see the flow."
          />
        ) : (
          <div>
            {recentFailures.map((run) => (
              <Link
                key={run.id}
                to={`/runs/${run.id}`}
                className="wc-activity"
                style={{ textDecoration: "none", color: "inherit" }}
              >
                <StatusBadge status={run.state} />
                <span className="wc-activity__monitor">
                  {monitors?.find((m) => m.id === run.monitor_id)?.name ??
                    "Unknown monitor"}
                </span>
                <span className="wc-activity__time">
                  {fmtRelative(run.ended_at ?? run.created_at)}
                </span>
                <span className="wc-activity__dur">
                  exit {run.exit_code ?? "n/a"}
                </span>
              </Link>
            ))}
          </div>
        )}
      </SurfaceCard>
    </>
  );
}

function countByStatus(monitors: Monitor[] | null) {
  const base = { healthy: 0, failing: 0, late: 0, paused: 0, unknown: 0 };
  if (!monitors) return base;
  for (const m of monitors) {
    if (m.status in base) (base as any)[m.status] += 1;
  }
  return base;
}
