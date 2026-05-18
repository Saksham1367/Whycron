import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { CodeBlock } from "@/components/CodeBlock";
import { Eyebrow } from "@/components/Eyebrow";
import { StatusBadge } from "@/components/StatusBadge";
import { SurfaceCard } from "@/components/SurfaceCard";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { api } from "@/lib/api";
import { config } from "@/lib/config";
import { fmtDuration, fmtRelative } from "@/lib/format";
import { formatSchedule } from "@/lib/schedule";
import type { MonitorDetail } from "@/lib/types";

export function MonitorDetailScreen() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { onSignOut, reloadAccount } = useOutletContext<ShellContext>();

  const [detail, setDetail] = useState<MonitorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    api
      .getMonitor(id)
      .then((d) => mounted && setDetail(d))
      .catch((e: Error) => mounted && setError(e.message));
    return () => {
      mounted = false;
    };
  }, [id]);

  if (!id) return null;

  async function togglePause() {
    if (!detail) return;
    const updated = await api.updateMonitor(detail.monitor.id, {
      paused: !detail.monitor.paused,
    });
    setDetail({ ...detail, monitor: { ...detail.monitor, ...updated } });
  }

  async function onDelete() {
    if (!detail) return;
    await api.deleteMonitor(detail.monitor.id);
    reloadAccount();
    navigate("/monitors", { replace: true });
  }

  const pingUrl = detail
    ? `${config.apiUrl}/p/${detail.monitor.ping_token}`
    : "";

  function copyPingUrl() {
    if (!pingUrl) return;
    navigator.clipboard
      .writeText(pingUrl)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1800);
      })
      .catch(() => undefined);
  }

  return (
    <>
      <Topbar
        crumbs={[
          { label: "Monitors", to: "/monitors" },
          { label: detail?.monitor.name ?? "Loading…", last: true },
        ]}
        onSignOut={onSignOut}
      />

      {error && <div className="wc-notice">{error}</div>}

      {!detail ? (
        <SurfaceCard>
          <p style={{ color: "var(--wc-text-muted)" }}>Loading monitor…</p>
        </SurfaceCard>
      ) : (
        <>
          <div className="wc-page-header">
            <div>
              <Eyebrow>Monitor</Eyebrow>
              <h1 className="wc-page-title">{detail.monitor.name}</h1>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: ".8rem",
                  marginTop: ".4rem",
                }}
              >
                <StatusBadge status={detail.monitor.status} />
                <span style={{ color: "var(--wc-text-muted)", fontSize: ".85rem" }}>
                  {formatSchedule(
                    detail.monitor.schedule_type,
                    detail.monitor.schedule_value,
                  )}{" "}
                  ({detail.monitor.timezone})
                </span>
              </div>
            </div>
            <div style={{ display: "flex", gap: ".6rem" }}>
              <Button
                variant="secondary"
                icon={detail.monitor.paused ? "play_arrow" : "pause"}
                onClick={togglePause}
              >
                {detail.monitor.paused ? "Resume" : "Pause"}
              </Button>
              <Button
                variant="danger"
                icon="delete"
                onClick={() => setConfirming(true)}
              >
                Delete
              </Button>
            </div>
          </div>

          {confirming && (
            <SurfaceCard variant="critical" style={{ marginBottom: "1.2rem" }}>
              <p style={{ margin: 0 }}>
                Soft-delete this monitor? Historical runs and explanations stay
                queryable but the monitor stops accepting pings.
              </p>
              <div style={{ display: "flex", gap: ".6rem", marginTop: ".8rem" }}>
                <Button variant="danger" icon="delete" onClick={onDelete}>
                  Yes, delete
                </Button>
                <Button variant="ghost" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </div>
            </SurfaceCard>
          )}

          <div className="wc-form-grid">
            <SurfaceCard>
              <Eyebrow>Ping URL</Eyebrow>
              <p
                style={{
                  color: "var(--wc-text-soft)",
                  margin: ".4rem 0 .8rem",
                  fontSize: ".88rem",
                }}
              >
                Have your job POST to this URL on success (or hit the{" "}
                <code>/start</code> and <code>/fail</code> variants).
              </p>
              <CodeBlock>{pingUrl}</CodeBlock>
              <div style={{ display: "flex", gap: ".6rem", marginTop: ".8rem" }}>
                <Button
                  variant="secondary"
                  icon={copied ? "check" : "content_copy"}
                  onClick={copyPingUrl}
                >
                  {copied ? "Copied" : "Copy URL"}
                </Button>
                <Link
                  to={`/failures?monitor_id=${detail.monitor.id}`}
                  className="wc-btn wc-btn--ghost"
                  style={{ textDecoration: "none" }}
                >
                  Failures for this monitor →
                </Link>
              </div>
            </SurfaceCard>

            <SurfaceCard>
              <Eyebrow>Recent runs</Eyebrow>
              <div style={{ marginTop: ".8rem" }}>
                {detail.recent_runs.length === 0 ? (
                  <p
                    style={{
                      color: "var(--wc-text-muted)",
                      margin: 0,
                      fontSize: ".88rem",
                    }}
                  >
                    No runs yet. Hit the ping URL to see your first heartbeat.
                  </p>
                ) : (
                  detail.recent_runs.map((r) => (
                    <Link
                      key={r.id}
                      to={`/runs/${r.id}`}
                      className="wc-activity"
                      style={{ textDecoration: "none", color: "inherit" }}
                    >
                      <StatusBadge status={r.state} />
                      <span className="wc-activity__monitor">
                        {fmtRelative(r.ended_at ?? r.started_at ?? r.created_at)}
                      </span>
                      <span style={{ color: "var(--wc-text-muted)" }}>
                        exit {r.exit_code ?? "—"}
                      </span>
                      <span className="wc-activity__dur">
                        {fmtDuration(r.duration_ms)}
                      </span>
                    </Link>
                  ))
                )}
              </div>
            </SurfaceCard>
          </div>
        </>
      )}
    </>
  );
}
