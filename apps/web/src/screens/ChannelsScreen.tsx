import { useEffect, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { Eyebrow } from "@/components/Eyebrow";
import { SurfaceCard } from "@/components/SurfaceCard";
import { SymbolIcon } from "@/components/SymbolIcon";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { api } from "@/lib/api";
import type {
  SlackChannelOption,
  SlackInstallationInfo,
} from "@/lib/api";
import type { ChannelType, NotificationChannel } from "@/lib/types";

const SLACK_ERROR_MESSAGES: Record<string, string> = {
  state_expired:
    "The Slack install link expired (10 minutes). Try connecting again.",
  exchange_failed:
    "Slack rejected the install. Double-check the app's redirect URL and scopes.",
  missing_code_or_state:
    "Slack didn't return a valid callback. Try connecting again.",
  access_denied: "You declined access in Slack.",
};

export function ChannelsScreen() {
  const { onSignOut, account } = useOutletContext<ShellContext>();
  const slackOAuthEnabled = account?.deployment.slack_oauth_enabled ?? true;
  const [searchParams, setSearchParams] = useSearchParams();
  const [channels, setChannels] = useState<NotificationChannel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [slack, setSlack] = useState<SlackInstallationInfo | null>(null);
  const [slackBusy, setSlackBusy] = useState(false);

  const slackConnectedFlag = searchParams.get("connected") === "slack";
  const slackErrorParam = searchParams.get("slack_error");

  function reload() {
    setChannels(null);
    api
      .listChannels()
      .then((r) => setChannels(r.items))
      .catch((e: Error) => setError(e.message));
    // Slack OAuth lives on the hosted product only — in self-host the
    // endpoint returns 503 so we skip the lookup entirely.
    if (slackOAuthEnabled) {
      api
        .getSlackInstallation()
        .then(setSlack)
        .catch(() => setSlack({ connected: false }));
    } else {
      setSlack({ connected: false });
    }
  }

  useEffect(reload, []);

  // Clear ?connected=slack / ?slack_error=... from the URL after we've shown
  // the banner once so a reload doesn't keep showing it.
  useEffect(() => {
    if (slackConnectedFlag || slackErrorParam) {
      const timer = window.setTimeout(() => {
        const next = new URLSearchParams(searchParams);
        next.delete("connected");
        next.delete("slack_error");
        setSearchParams(next, { replace: true });
      }, 6000);
      return () => window.clearTimeout(timer);
    }
  }, [slackConnectedFlag, slackErrorParam, searchParams, setSearchParams]);

  async function connectSlack() {
    setSlackBusy(true);
    try {
      const { authorize_url } = await api.startSlackInstall();
      window.location.href = authorize_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start Slack install");
      setSlackBusy(false);
    }
  }

  async function disconnectSlack() {
    if (
      !confirm(
        "Disconnect Slack? Any Slack notification channels will stop delivering until you reconnect.",
      )
    )
      return;
    setSlackBusy(true);
    try {
      await api.uninstallSlack();
      setSlack({ connected: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not disconnect Slack");
    } finally {
      setSlackBusy(false);
    }
  }

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

      {slackConnectedFlag && slack?.connected && (
        <div
          className="wc-notice"
          style={{
            marginBottom: "1.2rem",
            borderColor: "rgba(42,211,155,0.36)",
          }}
        >
          <strong>Slack connected:</strong> {slack.team_name}. Add a Slack
          channel below to start routing alerts.
        </div>
      )}

      {slackErrorParam && (
        <div className="wc-notice" style={{ marginBottom: "1.2rem" }}>
          <strong>Slack:</strong>{" "}
          {SLACK_ERROR_MESSAGES[slackErrorParam] ?? slackErrorParam}
        </div>
      )}

      {slackOAuthEnabled && (
        <SlackConnectionCard
          slack={slack}
          busy={slackBusy}
          onConnect={connectSlack}
          onDisconnect={disconnectSlack}
        />
      )}

      {creating && (
        <CreateChannelForm
          slackConnected={(slack?.connected ?? false) && slackOAuthEnabled}
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
          description="Add an email, webhook, Slack, or Discord channel so alerts reach you when a job breaks."
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
                name={channelIcon(c.type)}
                color="var(--wc-primary)"
              />
              <span className="wc-row__name">{c.name}</span>
              <span className="wc-row__meta">{channelMeta(c)}</span>
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

function channelIcon(type: string): string {
  switch (type) {
    case "email":
      return "mail";
    case "discord":
      return "chat";
    case "slack":
      return "tag";
    default:
      return "webhook";
  }
}

function channelMeta(c: NotificationChannel): string {
  const cfg = c.config as Record<string, unknown>;
  if (c.type === "slack") {
    const name = (cfg.channel_name as string) ?? (cfg.channel_id as string);
    return name ? `#${name.replace(/^#/, "")}` : "slack";
  }
  return (
    (cfg.to as string) ?? (cfg.url as string) ?? c.type
  );
}

function SlackConnectionCard({
  slack,
  busy,
  onConnect,
  onDisconnect,
}: {
  slack: SlackInstallationInfo | null;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  if (slack == null) {
    return null;
  }
  return (
    <SurfaceCard
      style={{
        marginBottom: "1.2rem",
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: "1rem",
        alignItems: "center",
      }}
    >
      <SymbolIcon name="tag" size="1.6rem" color="var(--wc-primary)" />
      <div>
        <strong>Slack workspace</strong>
        <div
          style={{
            color: "var(--wc-text-soft)",
            fontSize: ".85rem",
            marginTop: ".25rem",
          }}
        >
          {slack.connected ? (
            <>
              Connected to <strong>{slack.team_name}</strong>. Add a Slack
              channel below to route alerts.
            </>
          ) : (
            <>
              Connect your Slack workspace to send threaded alerts to any
              channel.
            </>
          )}
        </div>
      </div>
      {slack.connected ? (
        <Button
          variant="ghost"
          icon="link_off"
          onClick={onDisconnect}
          disabled={busy}
        >
          {busy ? "Working…" : "Disconnect"}
        </Button>
      ) : (
        <Button
          variant="primary"
          icon="add_link"
          onClick={onConnect}
          disabled={busy}
        >
          {busy ? "Opening Slack…" : "Connect Slack"}
        </Button>
      )}
    </SurfaceCard>
  );
}

function CreateChannelForm({
  slackConnected,
  onCancel,
  onCreated,
}: {
  slackConnected: boolean;
  onCancel: () => void;
  onCreated: () => void;
}) {
  const [type, setType] = useState<ChannelType>("email");
  const [name, setName] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [slackChannelId, setSlackChannelId] = useState("");
  const [slackChannelName, setSlackChannelName] = useState("");
  const [slackChannelOptions, setSlackChannelOptions] = useState<
    SlackChannelOption[] | null
  >(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (type !== "slack") return;
    if (!slackConnected) return;
    if (slackChannelOptions !== null) return;
    api
      .listSlackChannels()
      .then((r) => setSlackChannelOptions(r.channels))
      .catch((e: Error) =>
        setError(`Could not load Slack channels: ${e.message}`),
      );
  }, [type, slackConnected, slackChannelOptions]);

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
      if (type === "slack") {
        if (!slackChannelId) {
          throw new Error("Pick a Slack channel.");
        }
        config.channel_id = slackChannelId;
        if (slackChannelName) config.channel_name = slackChannelName;
      }
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
              <option value="slack" disabled={!slackConnected}>
                Slack{slackConnected ? "" : " (connect workspace first)"}
              </option>
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
              {type === "discord"
                ? "Discord webhook URL"
                : "Webhook URL (https://)"}
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

        {type === "slack" && (
          <label className="wc-field">
            <span className="wc-field__label">Slack channel</span>
            {slackChannelOptions == null ? (
              <p style={{ color: "var(--wc-text-muted)", margin: 0 }}>
                Loading channels…
              </p>
            ) : (
              <select
                className="wc-select"
                required
                value={slackChannelId}
                onChange={(e) => {
                  setSlackChannelId(e.target.value);
                  const match = slackChannelOptions.find(
                    (c) => c.id === e.target.value,
                  );
                  setSlackChannelName(match?.name ?? "");
                }}
              >
                <option value="" disabled>
                  Pick a channel…
                </option>
                {slackChannelOptions.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.is_private ? "🔒 " : "# "}
                    {c.name}
                    {c.is_private && !c.is_member ? " (invite the bot first)" : ""}
                  </option>
                ))}
              </select>
            )}
            <span
              style={{
                color: "var(--wc-text-muted)",
                fontSize: ".78rem",
                marginTop: ".3rem",
              }}
            >
              For private channels, run <code>/invite @Whycron</code> in
              Slack first so the bot can post.
            </span>
          </label>
        )}

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
