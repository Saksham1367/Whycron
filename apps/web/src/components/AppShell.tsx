import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { api } from "@/lib/api";
import type { Account } from "@/lib/types";
import { Sidebar } from "./Sidebar";
import { TermsAcceptanceModal } from "./TermsAcceptanceModal";

/**
 * App shell — sidebar + scrollable content. Loads the current account once
 * on mount and exposes it via the outlet context so screens can read tier,
 * usage, and the organization name without re-querying.
 *
 * Also gates the dashboard behind the terms-of-service modal: while the
 * user's accepted version doesn't match the published one, every screen
 * inside the shell is covered by a blocking acceptance modal.
 */
export function AppShell() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);

  function loadAccount() {
    api
      .getAccount()
      .then(setAccount)
      .catch((e: Error) => setError(e.message));
  }

  useEffect(() => {
    let mounted = true;
    api
      .getAccount()
      .then((data) => {
        if (mounted) setAccount(data);
      })
      .catch((e: Error) => {
        if (mounted) setError(e.message);
      });
    return () => {
      mounted = false;
    };
  }, []);

  async function onSignOut() {
    await signOut();
    navigate("/", { replace: true });
  }

  const needsTerms = account != null && !account.terms.is_up_to_date;

  return (
    <div className="wc-app">
      <Sidebar orgName={account?.organization_name ?? "Workspace"} />
      <main>
        {error && (
          <div className="wc-notice" style={{ margin: "1rem 1.6rem 0" }}>
            <strong>Couldn't load account:</strong> {error}
          </div>
        )}
        <div className="wc-content">
          <Outlet
            context={{
              account,
              onSignOut,
              reloadAccount: loadAccount,
            }}
          />
        </div>
      </main>
      {needsTerms && (
        <TermsAcceptanceModal
          currentVersion={account.terms.current_version}
          onAccepted={loadAccount}
        />
      )}
    </div>
  );
}

export interface ShellContext {
  account: Account | null;
  onSignOut: () => Promise<void>;
  reloadAccount: () => void;
}
