import { useEffect, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { Eyebrow } from "@/components/Eyebrow";
import { SurfaceCard } from "@/components/SurfaceCard";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { ApiError, api } from "@/lib/api";
import { track } from "@/lib/analytics";

export function AccountScreen() {
  const { account, onSignOut, reloadAccount } = useOutletContext<ShellContext>();
  const [searchParams] = useSearchParams();
  const [billingBusy, setBillingBusy] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);
  const justUpgraded = searchParams.get("upgraded") === "true";

  // If the URL says we just came back from Polar checkout, give the
  // webhook a few seconds to land then reload the account to show the
  // new tier without forcing the user to refresh.
  useEffect(() => {
    if (!justUpgraded) return;
    const timer = window.setTimeout(reloadAccount, 2500);
    return () => window.clearTimeout(timer);
  }, [justUpgraded, reloadAccount]);

  async function onUpgrade() {
    setBillingError(null);
    setBillingBusy(true);
    track("upgrade_clicked", { tier: "pro" });
    try {
      const { checkout_url } = await api.startCheckout("pro");
      window.location.href = checkout_url;
    } catch (err) {
      if (err instanceof ApiError) {
        setBillingError(err.message);
      } else {
        setBillingError(
          err instanceof Error ? err.message : "Could not open checkout",
        );
      }
      setBillingBusy(false);
    }
  }

  async function onManageBilling() {
    setBillingError(null);
    setBillingBusy(true);
    try {
      const { portal_url } = await api.openPortal();
      window.location.href = portal_url;
    } catch (err) {
      setBillingError(
        err instanceof Error ? err.message : "Could not open billing portal",
      );
      setBillingBusy(false);
    }
  }

  return (
    <>
      <Topbar
        crumbs={[{ label: "Account", last: true }]}
        onSignOut={onSignOut}
      />
      <div className="wc-page-header">
        <div>
          <Eyebrow>Workspace</Eyebrow>
          <h1 className="wc-page-title">Account</h1>
          <p className="wc-page-sub">
            Plan, usage, and the people who sign in here.
          </p>
        </div>
      </div>

      {justUpgraded && (
        <div
          className="wc-notice"
          style={{ marginBottom: "1.2rem", borderColor: "rgba(42,211,155,0.36)" }}
        >
          Thanks — your upgrade is being processed. The tier on this page
          updates automatically once Polar's confirmation lands (usually a
          few seconds).
        </div>
      )}

      {billingError && (
        <div className="wc-notice" style={{ marginBottom: "1.2rem" }}>
          <strong>Billing:</strong> {billingError}
        </div>
      )}

      {!account ? (
        <SurfaceCard>
          <p style={{ color: "var(--wc-text-muted)" }}>Loading account…</p>
        </SurfaceCard>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
          }}
        >
          <SurfaceCard>
            <Eyebrow>Profile</Eyebrow>
            <div style={{ marginTop: ".6rem", display: "flex", flexDirection: "column", gap: ".4rem" }}>
              <strong style={{ fontSize: "1.1rem" }}>{account.name ?? account.email}</strong>
              <span style={{ color: "var(--wc-text-soft)", fontSize: ".88rem" }}>
                {account.email}
              </span>
              <span style={{ color: "var(--wc-text-muted)", fontSize: ".82rem" }}>
                Role: {account.role}
              </span>
            </div>
            <hr className="wc-divider" />
            <Button variant="secondary" icon="logout" onClick={onSignOut}>
              Sign out
            </Button>
          </SurfaceCard>

          <SurfaceCard>
            <Eyebrow>Organization</Eyebrow>
            <div style={{ marginTop: ".6rem", display: "flex", flexDirection: "column", gap: ".4rem" }}>
              <strong style={{ fontSize: "1.1rem" }}>{account.organization_name}</strong>
              <span style={{ color: "var(--wc-text-muted)", fontSize: ".82rem" }}>
                Slug: {account.organization_slug}
              </span>
              <span style={{ color: "var(--wc-text-muted)", fontSize: ".82rem" }}>
                Tier: <strong style={{ color: "var(--wc-text)" }}>{account.tier}</strong>
              </span>
            </div>
          </SurfaceCard>

          <SurfaceCard style={{ gridColumn: "span 2" }}>
            <Eyebrow>Usage this month</Eyebrow>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
                marginTop: ".8rem",
              }}
            >
              <UsageMeter
                label="Active monitors"
                value={account.usage.monitors_active}
                limit={account.usage.monitors_limit}
              />
              <UsageMeter
                label="AI explanations"
                value={account.usage.ai_explanations_this_month}
                limit={account.usage.ai_explanations_monthly_limit}
              />
            </div>
            {(account.usage.monitors_limit > 0 &&
              account.usage.monitors_active >=
                account.usage.monitors_limit) ||
            (account.usage.ai_explanations_monthly_limit > 0 &&
              account.usage.ai_explanations_this_month >=
                account.usage.ai_explanations_monthly_limit) ? (
              <div
                className="wc-notice"
                style={{ marginTop: "1rem" }}
              >
                You're at the {account.tier} tier limit. Upgrade to Pro to
                lift it.
              </div>
            ) : null}
          </SurfaceCard>

          <SurfaceCard style={{ gridColumn: "span 2" }}>
            <Eyebrow>Billing</Eyebrow>
            {account.tier === "free" ? (
              <>
                <h3
                  style={{
                    font: "600 1.15rem var(--wc-font-body)",
                    letterSpacing: "-0.03em",
                    margin: ".5rem 0 .6rem",
                  }}
                >
                  Upgrade to Pro — $9 / month
                </h3>
                <p
                  style={{
                    color: "var(--wc-text-soft)",
                    margin: "0 0 1rem",
                    fontSize: ".9rem",
                    maxWidth: 540,
                  }}
                >
                  25 monitors · 1-minute resolution · 30-day history · all
                  notification channels · AI explanations on every failed run.
                </p>
                <Button
                  variant="primary"
                  icon="rocket_launch"
                  onClick={onUpgrade}
                  disabled={billingBusy}
                >
                  {billingBusy ? "Opening checkout…" : "Upgrade to Pro"}
                </Button>
              </>
            ) : (
              <>
                <h3
                  style={{
                    font: "600 1.15rem var(--wc-font-body)",
                    letterSpacing: "-0.03em",
                    margin: ".5rem 0 .6rem",
                  }}
                >
                  You're on the {account.tier} tier
                </h3>
                <p
                  style={{
                    color: "var(--wc-text-soft)",
                    margin: "0 0 1rem",
                    fontSize: ".9rem",
                  }}
                >
                  Manage your subscription, update your card, view past
                  invoices, or cancel — all from the Polar customer portal.
                </p>
                <Button
                  variant="secondary"
                  icon="receipt_long"
                  onClick={onManageBilling}
                  disabled={billingBusy}
                >
                  {billingBusy ? "Opening portal…" : "Manage billing"}
                </Button>
              </>
            )}
          </SurfaceCard>
        </div>
      )}
    </>
  );
}

function UsageMeter({
  label,
  value,
  limit,
}: {
  label: string;
  value: number;
  limit: number;
}) {
  const unlimited = limit < 0;
  const pct = unlimited
    ? 0
    : limit === 0
      ? 100
      : Math.min(100, Math.round((value / limit) * 100));
  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: ".4rem",
        }}
      >
        <span style={{ color: "var(--wc-text-soft)" }}>{label}</span>
        <span style={{ fontFamily: "var(--wc-font-code)" }}>
          {value} / {unlimited ? "∞" : limit}
        </span>
      </div>
      <div
        style={{
          height: 8,
          borderRadius: 999,
          background: "rgba(54,59,73,.55)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${unlimited ? 8 : pct}%`,
            height: "100%",
            background:
              pct >= 100 ? "var(--wc-danger)" : "var(--wc-primary-strong)",
            transition: "width 0.3s",
          }}
        />
      </div>
    </div>
  );
}
