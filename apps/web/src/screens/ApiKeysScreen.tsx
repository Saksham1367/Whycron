import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { Eyebrow } from "@/components/Eyebrow";
import { SurfaceCard } from "@/components/SurfaceCard";
import { SymbolIcon } from "@/components/SymbolIcon";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { ApiError, api } from "@/lib/api";
import type { ApiKey, ApiKeyCreated, ApiKeyScope } from "@/lib/api";

const ALL_SCOPES: { id: ApiKeyScope; label: string; help: string }[] = [
  {
    id: "monitors:read",
    label: "monitors:read",
    help: "List and view monitors.",
  },
  {
    id: "monitors:write",
    label: "monitors:write",
    help: "Create, edit, and delete monitors and notification channels.",
  },
  {
    id: "runs:read",
    label: "runs:read",
    help: "List and view run history and AI explanations.",
  },
  {
    id: "admin",
    label: "admin",
    help: "Full access including account, billing, and managing other API keys. Use sparingly.",
  },
];

export function ApiKeysScreen() {
  const { onSignOut } = useOutletContext<ShellContext>();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);

  function reload() {
    setKeys(null);
    api
      .listApiKeys()
      .then(setKeys)
      .catch((e: Error) => setError(e.message));
  }

  useEffect(reload, []);

  async function revoke(k: ApiKey) {
    if (
      !confirm(
        `Revoke the "${k.name}" key (${k.key_prefix}…)? Anything using it will start receiving 401 errors immediately.`,
      )
    )
      return;
    try {
      await api.revokeApiKey(k.id);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not revoke key");
    }
  }

  return (
    <>
      <Topbar
        crumbs={[
          { label: "Account", to: "/account" },
          { label: "API keys", last: true },
        ]}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>Account</Eyebrow>
          <h1 className="wc-page-title">API keys</h1>
          <p className="wc-page-sub">
            Programmatic access for CI/CD and SDKs. Send the key in the{" "}
            <code>X-Whycron-API-Key</code> header.
          </p>
        </div>
        <Button
          variant="primary"
          icon="add"
          onClick={() => {
            setJustCreated(null);
            setCreating(true);
          }}
        >
          New API key
        </Button>
      </div>

      {error && (
        <div className="wc-notice" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {justCreated && (
        <JustCreatedNotice
          minted={justCreated}
          onDismiss={() => setJustCreated(null)}
        />
      )}

      {creating && (
        <CreateApiKeyForm
          onCancel={() => setCreating(false)}
          onCreated={(minted) => {
            setCreating(false);
            setJustCreated(minted);
            reload();
          }}
        />
      )}

      {keys == null ? (
        <SurfaceCard>
          <p style={{ color: "var(--wc-text-muted)" }}>Loading…</p>
        </SurfaceCard>
      ) : keys.length === 0 ? (
        <EmptyState
          icon="vpn_key"
          title="No API keys yet"
          description="Create one to call the Whycron API from CI, scripts, or an SDK."
        />
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: ".7rem",
          }}
        >
          {keys.map((k) => (
            <ApiKeyRow key={k.id} apiKey={k} onRevoke={() => revoke(k)} />
          ))}
        </div>
      )}
    </>
  );
}

function ScopeBadges({ scopes }: { scopes: ApiKeyScope[] }) {
  return (
    <span style={{ display: "inline-flex", gap: ".35rem", flexWrap: "wrap" }}>
      {scopes.map((s) => (
        <code
          key={s}
          style={{
            padding: ".15rem .45rem",
            background: "rgba(64, 71, 90, .42)",
            borderRadius: 4,
            fontSize: ".74rem",
            color: "var(--wc-text-soft)",
          }}
        >
          {s}
        </code>
      ))}
    </span>
  );
}

function ApiKeyRow({
  apiKey,
  onRevoke,
}: {
  apiKey: ApiKey;
  onRevoke: () => void;
}) {
  const isRevoked = !!apiKey.revoked_at;
  const isExpired =
    !isRevoked &&
    !!apiKey.expires_at &&
    new Date(apiKey.expires_at) < new Date();
  const isActive = !isRevoked && !isExpired;

  const statusLabel = isRevoked ? "revoked" : isExpired ? "expired" : "active";
  const statusColor = isActive ? "var(--wc-primary-strong)" : "var(--wc-danger)";

  return (
    <SurfaceCard style={{ padding: "1rem 1.1rem" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: "1rem",
          alignItems: "flex-start",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: ".7rem",
              flexWrap: "wrap",
            }}
          >
            <strong style={{ fontSize: "1.02rem" }}>{apiKey.name}</strong>
            <code
              style={{
                color: "var(--wc-text-muted)",
                fontSize: ".82rem",
              }}
            >
              {apiKey.key_prefix}…
            </code>
            <span
              style={{
                fontSize: ".75rem",
                color: statusColor,
                textTransform: "uppercase",
                letterSpacing: ".05em",
                fontWeight: 600,
              }}
            >
              {statusLabel}
            </span>
          </div>

          <ScopeBadges scopes={apiKey.scopes} />

          <div
            style={{
              display: "flex",
              gap: "1.2rem",
              flexWrap: "wrap",
              color: "var(--wc-text-muted)",
              fontSize: ".78rem",
            }}
          >
            <span>Created {fmtAge(apiKey.created_at)}</span>
            <span>Last used {fmtAge(apiKey.last_used_at) ?? "never"}</span>
            {apiKey.expires_at && (
              <span>
                {isExpired ? "Expired" : "Expires"}{" "}
                {new Date(apiKey.expires_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        {!isRevoked && (
          <button
            type="button"
            onClick={onRevoke}
            title="Revoke this key"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: ".4rem",
              padding: ".45rem .7rem",
              background: "transparent",
              border: "1px solid rgba(231, 88, 92, .45)",
              borderRadius: 6,
              color: "var(--wc-danger)",
              fontSize: ".82rem",
              cursor: "pointer",
              transition: "background 0.15s, border-color 0.15s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(231, 88, 92, .1)";
              e.currentTarget.style.borderColor = "rgba(231, 88, 92, .75)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "rgba(231, 88, 92, .45)";
            }}
          >
            <SymbolIcon name="delete" size="1rem" />
            <span>Revoke</span>
          </button>
        )}
      </div>
    </SurfaceCard>
  );
}

function JustCreatedNotice({
  minted,
  onDismiss,
}: {
  minted: ApiKeyCreated;
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(minted.plaintext);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — user can still select+copy manually */
    }
  }
  return (
    <SurfaceCard
      style={{
        marginBottom: "1rem",
        borderColor: "rgba(42, 211, 155, .42)",
        background: "rgba(42, 211, 155, .06)",
      }}
    >
      <Eyebrow>New key — copy it now</Eyebrow>
      <p
        style={{
          color: "var(--wc-text-soft)",
          margin: ".5rem 0",
          fontSize: ".88rem",
        }}
      >
        This is the only time the full key value is shown. We hash it on save
        and never store the plaintext — if you lose it, you'll need to make a
        new one.
      </p>
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
          marginBottom: ".7rem",
          overflow: "auto",
        }}
      >
        <span style={{ flex: 1, wordBreak: "break-all" }}>
          {minted.plaintext}
        </span>
        <Button variant="secondary" icon={copied ? "check" : "content_copy"} onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <Button variant="ghost" onClick={onDismiss}>
        I've saved it
      </Button>
    </SurfaceCard>
  );
}

function CreateApiKeyForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void;
  onCreated: (minted: ApiKeyCreated) => void;
}) {
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<Set<ApiKeyScope>>(
    new Set(["monitors:read"]),
  );
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function toggleScope(s: ApiKeyScope) {
    setScopes((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!name.trim()) {
      setFormError("Give the key a name so you can identify it later.");
      return;
    }
    if (scopes.size === 0) {
      setFormError("Pick at least one scope.");
      return;
    }
    setSubmitting(true);
    try {
      const minted = await api.createApiKey({
        name: name.trim(),
        scopes: [...scopes],
      });
      onCreated(minted);
    } catch (err) {
      if (err instanceof ApiError) setFormError(err.message);
      else setFormError(err instanceof Error ? err.message : "Could not create key");
      setSubmitting(false);
    }
  }

  return (
    <SurfaceCard style={{ marginBottom: "1rem" }}>
      <form onSubmit={submit}>
        <Eyebrow>New API key</Eyebrow>
        <div style={{ marginTop: ".7rem", display: "flex", flexDirection: "column", gap: ".7rem" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: ".3rem" }}>
            <span style={{ color: "var(--wc-text-soft)", fontSize: ".82rem" }}>
              Name
            </span>
            <input
              className="wc-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ci-deploy or laptop-script"
              maxLength={120}
              autoFocus
            />
          </label>
          <div>
            <span style={{ color: "var(--wc-text-soft)", fontSize: ".82rem" }}>
              Scopes
            </span>
            <div style={{ marginTop: ".4rem", display: "flex", flexDirection: "column", gap: ".4rem" }}>
              {ALL_SCOPES.map((s) => (
                <label
                  key={s.id}
                  style={{ display: "flex", gap: ".55rem", alignItems: "flex-start", cursor: "pointer" }}
                >
                  <input
                    type="checkbox"
                    checked={scopes.has(s.id)}
                    onChange={() => toggleScope(s.id)}
                    style={{ marginTop: ".2rem" }}
                  />
                  <div>
                    <code style={{ fontWeight: 600 }}>{s.label}</code>
                    <div style={{ color: "var(--wc-text-muted)", fontSize: ".78rem" }}>
                      {s.help}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>
          {formError && (
            <div className="wc-notice">{formError}</div>
          )}
          <div style={{ display: "flex", gap: ".5rem" }}>
            <Button
              type="submit"
              variant="primary"
              icon="check"
              disabled={submitting}
            >
              {submitting ? "Creating…" : "Create key"}
            </Button>
            <Button variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </div>
      </form>
    </SurfaceCard>
  );
}

function fmtAge(iso: string | null): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
