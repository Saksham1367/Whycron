import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ErrorBoundary, initAnalytics } from "./lib/analytics";

import "./styles/tokens.css";
import "./styles/app.css";

// Initialize Sentry + PostHog before React boots so early errors and the
// initial page view are captured. Both are no-ops when their env vars
// aren't configured.
initAnalytics();

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element in index.html");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary
      fallback={({ resetError }) => (
        <div
          style={{
            minHeight: "100vh",
            display: "grid",
            placeItems: "center",
            padding: "2rem",
            textAlign: "center",
            color: "var(--wc-text)",
          }}
        >
          <div style={{ maxWidth: 480 }}>
            <p
              style={{
                color: "var(--wc-danger)",
                fontWeight: 700,
                fontSize: "0.72rem",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
              }}
            >
              Something broke
            </p>
            <h1
              style={{
                font: "600 1.6rem var(--wc-font-body)",
                letterSpacing: "-0.03em",
                margin: ".4rem 0 1rem",
              }}
            >
              The dashboard crashed.
            </h1>
            <p style={{ color: "var(--wc-text-soft)", marginBottom: "1.2rem" }}>
              Whycron's error tracker received the report. Reload the page to
              try again.
            </p>
            <button
              className="wc-btn wc-btn--primary"
              onClick={() => {
                resetError();
                window.location.reload();
              }}
            >
              Reload
            </button>
          </div>
        </div>
      )}
    >
      <App />
    </ErrorBoundary>
  </StrictMode>
);
