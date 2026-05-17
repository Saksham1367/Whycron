import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { api } from "@/lib/api";
import type { Account } from "@/lib/types";
import { Sidebar } from "./Sidebar";

/**
 * App shell — sidebar + scrollable content. Loads the current account once
 * on mount and exposes it via the outlet context so screens can read tier,
 * usage, and the organization name without re-querying.
 */
export function AppShell() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    navigate("/login", { replace: true });
  }

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
          <Outlet context={{ account, onSignOut, reloadAccount: () => {
            api.getAccount().then(setAccount).catch(() => {});
          } }} />
        </div>
      </main>
    </div>
  );
}

export interface ShellContext {
  account: Account | null;
  onSignOut: () => Promise<void>;
  reloadAccount: () => void;
}
