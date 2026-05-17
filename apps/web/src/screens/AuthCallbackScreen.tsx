import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";

/**
 * Lands here after the OAuth provider (e.g. Google) redirects back. The
 * Supabase JS client picks up the access token from the URL fragment
 * automatically and emits an auth state change; we just wait for the
 * session to populate and then bounce to the dashboard.
 */
export function AuthCallbackScreen() {
  const navigate = useNavigate();
  const { session, loading } = useAuth();

  useEffect(() => {
    if (!loading) {
      navigate(session ? "/" : "/login", { replace: true });
    }
  }, [loading, session, navigate]);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        color: "var(--wc-text-muted)",
      }}
    >
      Signing you in…
    </div>
  );
}
