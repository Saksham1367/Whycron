import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { Button } from "@/components/Button";
import { Eyebrow } from "@/components/Eyebrow";
import { SurfaceCard } from "@/components/SurfaceCard";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { ApiError, api } from "@/lib/api";

export function CreateMonitorScreen() {
  const navigate = useNavigate();
  const { onSignOut, reloadAccount } = useOutletContext<ShellContext>();

  const [name, setName] = useState("");
  const [scheduleType, setScheduleType] = useState<
    "cron" | "interval" | "on_demand"
  >("cron");
  const [scheduleValue, setScheduleValue] = useState("0 2 * * *");
  const [timezone, setTimezone] = useState("UTC");
  const [graceSeconds, setGraceSeconds] = useState(60);
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const monitor = await api.createMonitor({
        name,
        schedule_type: scheduleType,
        schedule_value: scheduleValue,
        timezone,
        grace_period_seconds: graceSeconds,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      reloadAccount();
      navigate(`/monitors/${monitor.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Create failed");
      }
      setBusy(false);
    }
  }

  return (
    <>
      <Topbar
        crumbs={[
          { label: "Monitors", to: "/monitors" },
          { label: "New monitor", last: true },
        ]}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>Create</Eyebrow>
          <h1 className="wc-page-title">New monitor</h1>
          <p className="wc-page-sub">
            Register a scheduled job. Whycron generates a ping URL — your job
            hits it on every run.
          </p>
        </div>
      </div>

      <div className="wc-form-grid">
        <SurfaceCard>
          <form
            onSubmit={onSubmit}
            style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
          >
            <label className="wc-field">
              <span className="wc-field__label">Name</span>
              <input
                className="wc-input"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nightly PostgreSQL backup"
                autoFocus
              />
            </label>

            <label className="wc-field">
              <span className="wc-field__label">Schedule type</span>
              <select
                className="wc-select"
                value={scheduleType}
                onChange={(e) =>
                  setScheduleType(e.target.value as typeof scheduleType)
                }
              >
                <option value="cron">Cron expression</option>
                <option value="interval">Interval (seconds)</option>
                <option value="on_demand">On demand (no schedule)</option>
              </select>
            </label>

            <label className="wc-field">
              <span className="wc-field__label">
                {scheduleType === "cron"
                  ? "Cron expression"
                  : scheduleType === "interval"
                    ? "Seconds between runs"
                    : "Schedule value"}
              </span>
              <input
                className="wc-input"
                required
                value={scheduleValue}
                onChange={(e) => setScheduleValue(e.target.value)}
                placeholder={scheduleType === "cron" ? "0 2 * * *" : "300"}
                style={{ fontFamily: "var(--wc-font-code)" }}
              />
            </label>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
              }}
            >
              <label className="wc-field">
                <span className="wc-field__label">Timezone</span>
                <input
                  className="wc-input"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  placeholder="UTC"
                />
              </label>
              <label className="wc-field">
                <span className="wc-field__label">Grace period (seconds)</span>
                <input
                  className="wc-input"
                  type="number"
                  min={0}
                  max={86_400}
                  value={graceSeconds}
                  onChange={(e) => setGraceSeconds(Number(e.target.value))}
                />
              </label>
            </div>

            <label className="wc-field">
              <span className="wc-field__label">Tags (comma-separated)</span>
              <input
                className="wc-input"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="db, backup, nightly"
              />
            </label>

            {error && (
              <p
                style={{
                  color: "var(--wc-danger)",
                  margin: 0,
                  fontSize: ".85rem",
                }}
              >
                {error}
              </p>
            )}

            <div style={{ display: "flex", gap: ".8rem", marginTop: ".4rem" }}>
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? "Creating…" : "Create monitor"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => navigate(-1)}
              >
                Cancel
              </Button>
            </div>
          </form>
        </SurfaceCard>

        <SurfaceCard>
          <Eyebrow>Heartbeat preview</Eyebrow>
          <h3
            style={{
              font: "600 1.05rem var(--wc-font-body)",
              letterSpacing: "-0.02em",
              margin: ".5rem 0 .8rem",
            }}
          >
            After you create this monitor
          </h3>
          <p
            style={{
              color: "var(--wc-text-soft)",
              margin: 0,
              fontSize: ".88rem",
            }}
          >
            You'll get a ping URL like{" "}
            <code
              style={{
                fontFamily: "var(--wc-font-code)",
                color: "var(--wc-text)",
                background: "rgba(4,7,12,.6)",
                padding: "2px 6px",
                borderRadius: 6,
              }}
            >
              {`POST https://whycron.dev/p/<token>`}
            </code>{" "}
            and the start/fail variants. Hit it from your job; failures with
            log payloads get a plain-English AI explanation in the alert.
          </p>
        </SurfaceCard>
      </div>
    </>
  );
}
