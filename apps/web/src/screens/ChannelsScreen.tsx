import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { Eyebrow } from "@/components/Eyebrow";
import { SurfaceCard } from "@/components/SurfaceCard";
import { SymbolIcon } from "@/components/SymbolIcon";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { api } from "@/lib/api";
import type { ChannelType, NotificationChannel } from "@/lib/types";

export function ChannelsScreen() {
  const { onSignOut } = useOutletContext<ShellContext>();
  const [channels, setChannels] = useState<NotificationChannel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  function reload() {
    setChannels(null);
    api
      .listChannels()
      .then((r) => setChannels(r.items))
      .catch((e: Error) => setError(e.message));
  }

  useEffect(reload, []);

  async function toggle(c: NotificationChannel) {
    await api.updateChannel(c.id, { enabled: !c.enabled });
    reload();
  }

  async function remove(c: NotificationChannel) {
    if (!confirm(`Delete the "${c.name}" channel? Existing delivery history is kept.`))
      return;
    await api.deleteChannel(c.id);
    reload();
  }

  return (
    <>
      <Topbar
        crumbs={[{ label: "Notifications", last: true }]}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>Workspace</Eyebrow>
          <h1 className="wc-page-title">Notification channels</h1>
          <p className="wc-page-sub">
            Where alerts go when a monitor fails, misses, or times out.
          </p>
        </div>
        <Button
          variant="primary"
          icon="add"
          onClick={() => setCreating(true)}
        >
          Add channel
        </Button>
      </div>

      {error && <div className="wc-notice">{error}</div>}

      {creating && (
        <CreateChannelForm
          onCancel={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            reload();
          }}
        />
      )}

      {channels == null ? (
        <SurfaceCard>
          <p style={{ color: "var(--wc-text-muted)" }}>Loading…</p>
        </SurfaceCard>
      ) : channels.length === 0 ? (
        <EmptyState
          icon="notifications"
          title="No notification channels"
          description="Add an email, webhook, or Discord channel so alerts reach you when a job breaks."
          action={
            <Button
              variant="primary"
              icon="add"
              onClick={() => setCreating(true)}
            >
              Add the first one
            </Button>
          }
        />
      ) : (
        <SurfaceCard>
          {channels.map((c) => (
            <div
              key={c.id}
              className="wc-row"
              style={{ gridTemplateColumns: "auto 1.6fr 1fr auto auto" }}
            >
              <SymbolIcon
                name={
                  c.type === "email"
                    ? "mail"
                    : c.type === "discord"
                      ? "chat"
                      : "webhook"
                }
                color="var(--wc-primary)"
              />
              <span className="wc-row__name">{c.name}</span>
              <span className="wc-row__meta">
                {(c.config as Record<string, unknown>).to as string ??
                  (c.config as Record<string, unknown>).url as string ??
                  c.type}
              </span>
              <Button
                variant={c.enabled ? "secondary" : "ghost"}
                onClick={() => toggle(c)}
              >
                {c.enabled ? "Enabled" : "Disabled"}
              </Button>
              <Button variant="danger" icon="delete" onClick={() => remove(c)}>
                Delete
              </Button>
            </div>
          ))}
        </SurfaceCard>
      )}
    </>
  );
}

function CreateChannelForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: () => void;
}) {
  const [type, setType] = useState<ChannelType>("email");
  const [name, setName] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const config: Record<string, unknown> = {};
      if (type === "email") config.to = emailTo;
      if (type === "webhook") {
        config.url = url;
        if (secret) config.secret = secret;
      }
      if (type === "discord") config.url = url;
      await api.createChannel({ type, name, config });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
      setBusy(false);
    }
  }

  return (
    <SurfaceCard style={{ marginBottom: "1.2rem" }}>
      <Eyebrow>New channel</Eyebrow>
      <form
        onSubmit={submit}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          marginTop: ".6rem",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
          }}
        >
          <label className="wc-field">
            <span className="wc-field__label">Type</span>
            <select
              className="wc-select"
              value={type}
              onChange={(e) => setType(e.target.value as ChannelType)}
            >
              <option value="email">Email</option>
              <option value="webhook">Webhook (HMAC-signed)</option>
              <option value="discord">Discord</option>
            </select>
          </label>
          <label className="wc-field">
            <span className="wc-field__label">Name</span>
            <input
              className="wc-input"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ops inbox"
            />
          </label>
        </div>

        {type === "email" && (
          <label className="wc-field">
            <span className="wc-field__label">Email address</span>
            <input
              className="wc-input"
              type="email"
              required
              value={emailTo}
              onChange={(e) => setEmailTo(e.target.value)}
              placeholder="alerts@your-team.com"
            />
          </label>
        )}

        {(type === "webhook" || type === "discord") && (
          <label className="wc-field">
            <span className="wc-field__label">
              {type === "discord" ? "Discord webhook URL" : "Webhook URL (https://)"}
            </span>
            <input
              className="wc-input"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://…"
            />
          </label>
        )}

        {type === "webhook" && (
          <label className="wc-field">
            <span className="wc-field__label">
              HMAC signing secret (optional — uses global if omitted)
            </span>
            <input
              className="wc-input"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="long random string"
            />
          </label>
        )}

        {error && (
          <p style={{ color: "var(--wc-danger)", margin: 0, fontSize: ".85rem" }}>
            {error}
          </p>
        )}

        <div style={{ display: "flex", gap: ".6rem" }}>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Adding…" : "Add channel"}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </SurfaceCard>
  );
}
