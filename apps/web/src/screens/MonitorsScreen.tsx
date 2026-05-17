import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { Eyebrow } from "@/components/Eyebrow";
import { StatusBadge } from "@/components/StatusBadge";
import { SurfaceCard } from "@/components/SurfaceCard";
import { SymbolIcon } from "@/components/SymbolIcon";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { api } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import type { Monitor } from "@/lib/types";

const STATUS_FILTERS = [
  { id: "", label: "All" },
  { id: "healthy", label: "Healthy" },
  { id: "failing", label: "Failing" },
  { id: "late", label: "Late" },
  { id: "paused", label: "Paused" },
  { id: "unknown", label: "Unknown" },
];

export function MonitorsScreen() {
  const navigate = useNavigate();
  const { onSignOut } = useOutletContext<ShellContext>();
  const [monitors, setMonitors] = useState<Monitor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let mounted = true;
    setMonitors(null);
    api
      .listMonitors({
        status: statusFilter || undefined,
        search: search || undefined,
        limit: 200,
      })
      .then((r) => {
        if (mounted) setMonitors(r.items);
      })
      .catch((e: Error) => {
        if (mounted) setError(e.message);
      });
    return () => {
      mounted = false;
    };
  }, [statusFilter, search]);

  return (
    <>
      <Topbar
        crumbs={[{ label: "Monitors", last: true }]}
        onCreate={() => navigate("/monitors/new")}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>Workspace</Eyebrow>
          <h1 className="wc-page-title">Monitors</h1>
          <p className="wc-page-sub">
            Every registered cron job and its current health.
          </p>
        </div>
      </div>

      <div className="wc-cluster" style={{ marginBottom: "1rem" }}>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            className={`wc-pill ${statusFilter === f.id ? "wc-pill--active" : ""}`}
            onClick={() => setStatusFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
        <label className="wc-search" style={{ marginLeft: "auto" }}>
          <SymbolIcon name="search" size="1.05rem" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name"
          />
        </label>
      </div>

      {error && (
        <div className="wc-notice" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {monitors == null ? (
        <SurfaceCard>
          <p style={{ color: "var(--wc-text-muted)" }}>Loading monitors…</p>
        </SurfaceCard>
      ) : monitors.length === 0 ? (
        <EmptyState
          icon="timer"
          title="No monitors yet"
          description="Create one to start receiving heartbeats from your scheduled jobs."
          action={
            <Link
              to="/monitors/new"
              className="wc-btn wc-btn--primary"
              style={{ textDecoration: "none" }}
            >
              <SymbolIcon name="add" size="1.05rem" /> New monitor
            </Link>
          }
        />
      ) : (
        <SurfaceCard>
          {monitors.map((m) => (
            <Link
              key={m.id}
              to={`/monitors/${m.id}`}
              className="wc-row"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <span className="wc-row__name">{m.name}</span>
              <span className="wc-row__schedule">
                {m.schedule_type === "cron" ? m.schedule_value : m.schedule_type}
              </span>
              <span className="wc-row__meta">{m.timezone}</span>
              <StatusBadge status={m.status} />
              <span className="wc-row__meta">
                Updated {fmtRelative(m.updated_at)}
              </span>
              <SymbolIcon name="chevron_right" color="var(--wc-text-muted)" />
            </Link>
          ))}
        </SurfaceCard>
      )}
    </>
  );
}
