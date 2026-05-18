import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/Button";
import { Eyebrow } from "@/components/Eyebrow";
import { SurfaceCard } from "@/components/SurfaceCard";
import { SymbolIcon } from "@/components/SymbolIcon";

type Mode = "signin" | "signup";

export function LoginScreen() {
  const { session, signInWithGoogle, signInWithEmail, signUpWithEmail } =
    useAuth();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  // The landing-page "Sign up" button links here with ?mode=signup so the
  // form opens already in signup mode (terms checkbox visible).
  const [mode, setMode] = useState<Mode>(
    searchParams.get("mode") === "signup" ? "signup" : "signin",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  // Detect Supabase signup hint in URL fragment (after email confirmation).
  useEffect(() => {
    if (window.location.hash.includes("type=signup")) {
      setInfo("Email confirmed. You can sign in now.");
    }
  }, []);

  if (session) return <Navigate to={from} replace />;

  // For signup, the user must explicitly check the T&C box. The backend
  // also enforces this via a blocking modal on first dashboard load, so
  // OAuth signups (where this checkbox isn't shown again) are caught
  // server-side. The checkbox here is the primary, paper-trail
  // acceptance moment per CONTEXT.md.
  const signupBlocked = mode === "signup" && !acceptedTerms;

  async function onGoogle() {
    if (signupBlocked) {
      setError("Tick the Terms & Privacy box before signing up.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await signInWithGoogle();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
      setBusy(false);
    }
  }

  async function onEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (signupBlocked) {
      setError("Tick the Terms & Privacy box before creating an account.");
      return;
    }
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      if (mode === "signin") {
        await signInWithEmail(email, password);
      } else {
        await signUpWithEmail(email, password);
        setInfo(
          "Check your inbox for a confirmation link, then come back here to sign in."
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "2rem",
      }}
    >
      <SurfaceCard
        style={{ width: "100%", maxWidth: 420, padding: "2rem" }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: ".55rem",
            marginBottom: ".4rem",
          }}
        >
          <strong className="wc-wordmark">whycron</strong>
        </div>
        <Eyebrow>Sign in</Eyebrow>
        <h1
          style={{
            font: "600 1.6rem var(--wc-font-body)",
            letterSpacing: "-0.03em",
            margin: ".4rem 0 1.4rem",
          }}
        >
          Cron monitoring that tells you why
        </h1>

        <Button
          variant="secondary"
          onClick={onGoogle}
          icon="login"
          style={{ width: "100%", justifyContent: "center" }}
        >
          {busy ? "Redirecting…" : "Continue with Google"}
        </Button>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: ".6rem",
            margin: "1.2rem 0",
            color: "var(--wc-text-muted)",
            fontSize: ".75rem",
          }}
        >
          <hr
            style={{
              flex: 1,
              border: 0,
              borderTop: "1px solid rgba(54,59,73,.55)",
            }}
          />
          OR EMAIL
          <hr
            style={{
              flex: 1,
              border: 0,
              borderTop: "1px solid rgba(54,59,73,.55)",
            }}
          />
        </div>

        <form
          onSubmit={onEmailSubmit}
          style={{ display: "flex", flexDirection: "column", gap: ".8rem" }}
        >
          <label className="wc-field">
            <span className="wc-field__label">Email</span>
            <input
              className="wc-input"
              type="email"
              value={email}
              required
              autoComplete="email"
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </label>
          <label className="wc-field">
            <span className="wc-field__label">Password</span>
            <input
              className="wc-input"
              type="password"
              value={password}
              required
              minLength={8}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </label>
          {mode === "signup" && (
            <label
              style={{
                display: "flex",
                gap: ".55rem",
                alignItems: "flex-start",
                color: "var(--wc-text-soft)",
                fontSize: ".82rem",
                cursor: "pointer",
                margin: ".2rem 0",
              }}
            >
              <input
                type="checkbox"
                checked={acceptedTerms}
                onChange={(e) => setAcceptedTerms(e.target.checked)}
                style={{ marginTop: ".15rem", flexShrink: 0 }}
                required
              />
              <span>
                I agree to the{" "}
                <Link to="/terms" target="_blank" rel="noreferrer">
                  Terms of Service
                </Link>{" "}
                and{" "}
                <Link to="/privacy" target="_blank" rel="noreferrer">
                  Privacy Policy
                </Link>
                .
              </span>
            </label>
          )}
          {error && (
            <p
              style={{
                color: "var(--wc-danger)",
                fontSize: ".82rem",
                margin: 0,
              }}
            >
              <SymbolIcon name="error" size="0.95rem" /> {error}
            </p>
          )}
          {info && (
            <p
              style={{
                color: "var(--wc-success)",
                fontSize: ".82rem",
                margin: 0,
              }}
            >
              {info}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            disabled={busy || signupBlocked}
            style={{ width: "100%", justifyContent: "center" }}
          >
            {busy
              ? "…"
              : mode === "signin"
                ? "Sign in"
                : "Create account"}
          </Button>
        </form>

        <p
          style={{
            textAlign: "center",
            marginTop: "1.2rem",
            color: "var(--wc-text-soft)",
            fontSize: ".82rem",
          }}
        >
          {mode === "signin" ? (
            <>
              No account yet?{" "}
              <button
                type="button"
                onClick={() => setMode("signup")}
                style={{
                  background: "none",
                  border: 0,
                  color: "var(--wc-primary)",
                  cursor: "pointer",
                  font: "inherit",
                  padding: 0,
                }}
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => setMode("signin")}
                style={{
                  background: "none",
                  border: 0,
                  color: "var(--wc-primary)",
                  cursor: "pointer",
                  font: "inherit",
                  padding: 0,
                }}
              >
                Sign in
              </button>
            </>
          )}
        </p>
      </SurfaceCard>
    </div>
  );
}
