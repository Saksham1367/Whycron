import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/Button";
import { Eyebrow } from "@/components/Eyebrow";
import { SurfaceCard } from "@/components/SurfaceCard";
import { SymbolIcon } from "@/components/SymbolIcon";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { ApiError, api } from "@/lib/api";
import type { StatusPageConfig } from "@/lib/api";
import type { Monitor } from "@/lib/types";

export function StatusPageScreen() {
  const { onSignOut } = useOutletContext<ShellContext>();
  const [config, setConfig] = useState<StatusPageConfig | null>(null);
  const [monitors, setMonitors] = useState<Monitor[] | null>(null);
  const [slug, setSlug] = useState("");
  const [headline, setHeadline] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okFlash, setOkFlash] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function reload() {
    setError(null);
    api
      .getStatusPageConfig()
      .then((c) => {
        setConfig(c);
        setSlug(c.slug ?? "");
        setHeadline(c.headline ?? "");
      })
      .catch((e: Error) =>
        setError(e instanceof ApiError ? e.message : e.message),
      );
    api
      .listMonitors({ limit: 200 })
      .then((r) => setMonitors(r.items))
      .catch(() => setMonitors([]));
  }

  useEffect(reload, []);

  async function save() {
    setError(null);
    setBusy(true);
    try {
      const next = await api.updateStatusPageConfig({
        slug: slug.trim() === "" ? null : slug.trim(),
        headline: headline.trim() === "" ? null : headline.trim(),
      });
      setConfig(next);
      setOkFlash("Saved.");
      window.setTimeout(() => setOkFlash(null), 2500);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not save status page config",
      );
    } finally {
      setBusy(false);
    }
  }

  async function togglePublic(m: Monitor, next: boolean) {
    try {
      const updated = await api.updateMonitor(m.id, { is_public: next });
      setMonitors((prev) =>
        prev?.map((row) => (row.id === m.id ? updated : row)) ?? prev,
      );
      // Refresh the counts.
      api.getStatusPageConfig().then(setConfig).catch(() => {});
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not toggle monitor",
      );
    }
  }

  async function copyUrl() {
    if (!config?.public_url) return;
    try {
      await navigator.clipboard.writeText(config.public_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  }

  return (
    <>
      <Topbar
        crumbs={[
          { label: "Account", to: "/account" },
          { label: "Status page", last: true },
        ]}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>Account</Eyebrow>
          <h1 className="wc-page-title">Public status page</h1>
          <p className="wc-page-sub">
            Opt-in per monitor. The page is unauthenticated and cached at
            the edge — share the URL with anyone.
          </p>
        </div>
      </div>

      {error && (
        <div className="wc-notice" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {okFlash && (
        <div
          className="wc-notice"
          style={{
            marginBottom: "1rem",
            borderColor: "rgba(42,211,155,0.36)",
          }}
        >
          {okFlash}
        </div>
      )}

      <SurfaceCard style={{ marginBottom: "1rem" }}>
        <Eyebrow>URL</Eyebrow>
        <div
          style={{
            marginTop: ".6rem",
            display: "grid",
            gridTemplateColumns: "1fr",
            gap: ".7rem",
          }}
        >
          <label className="wc-field">
            <span className="wc-field__label">Slug</span>
            <input
              className="wc-input"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase())}
              placeholder="e.g. acme"
              maxLength={40}
            />
            <span
              style={{
                color: "var(--wc-text-muted)",
                fontSize: ".75rem",
                marginTop: ".25rem",
              }}
            >
              3–40 chars, lowercase letters, digits, single dashes. Start
              with a letter. Leave blank to disable the page.
            </span>
          </label>

          <label className="wc-field">
            <span className="wc-field__label">Headline (optional)</span>
            <input
              className="wc-input"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="A short tagline shown above the monitor list."
              maxLength={200}
            />
          </label>

          {config?.public_url && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: ".5rem",
                background: "rgba(0,0,0,.32)",
                padding: ".55rem .65rem",
                borderRadius: 6,
                fontFamily: "var(--wc-font-code)",
                fontSize: ".82rem",
              }}
            >
              <span style={{ flex: 1, wordBreak: "break-all" }}>
                {config.public_url}
              </span>
              <Button
                variant="secondary"
                icon={copied ? "check" : "content_copy"}
                onClick={copyUrl}
              >
                {copied ? "Copied" : "Copy"}
              </Button>
              <a
                href={config.public_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: ".3rem",
                  color: "var(--wc-text-soft)",
                  textDecoration: "none",
                  fontSize: ".82rem",
                }}
              >
                <SymbolIcon name="open_in_new" size=".95rem" />
                Open
              </a>
            </div>
          )}

          <div style={{ display: "flex", gap: ".5rem" }}>
            <Button
              variant="primary"
              icon="save"
              onClick={save}
              disabled={busy}
            >
              {busy ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setSlug(config?.slug ?? "");
                setHeadline(config?.headline ?? "");
              }}
              disabled={busy}
            >
              Reset
            </Button>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard>
        <Eyebrow>Monitors on the public page</Eyebrow>
        <p
          style={{
            color: "var(--wc-text-soft)",
            margin: ".4rem 0 .9rem",
            fontSize: ".88rem",
          }}
        >
          {config
            ? `${config.public_monitor_count} of ${config.total_monitor_count} monitors are public.`
            : "Loading…"}
        </p>

        {monitors == null ? (
          <p style={{ color: "var(--wc-text-muted)" }}>Loading monitors…</p>
        ) : monitors.length === 0 ? (
          <p style={{ color: "var(--wc-text-muted)" }}>
            No monitors yet. Create one first, then flip its public toggle here.
          </p>
        ) : (
          <div
            style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}
          >
            {monitors.map((m) => (
              <MonitorRow
                key={m.id}
                monitor={m}
                onToggle={(next) => togglePublic(m, next)}
              />
            ))}
          </div>
        )}
      </SurfaceCard>
    </>
  );
}

function MonitorRow({
  monitor,
  onToggle,
}: {
  monitor: Monitor;
  onToggle: (next: boolean) => void;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: "1rem",
        alignItems: "center",
        padding: ".75rem .9rem",
        borderRadius: 8,
        background: "rgba(255,255,255,.02)",
        border: "1px solid var(--wc-border)",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: ".25rem" }}>
        <strong>{monitor.name}</strong>
        <span
          style={{
            color: "var(--wc-text-muted)",
            fontSize: ".78rem",
            fontFamily: "var(--wc-font-code)",
          }}
        >
          {monitor.schedule_type} · {monitor.schedule_value} ·{" "}
          <em style={{ fontStyle: "normal" }}>{monitor.status}</em>
        </span>
      </div>
      <Button
        variant={monitor.is_public ? "primary" : "ghost"}
        icon={monitor.is_public ? "visibility" : "visibility_off"}
        onClick={() => onToggle(!monitor.is_public)}
      >
        {monitor.is_public ? "Public" : "Private"}
      </Button>
    </div>
  );
}
