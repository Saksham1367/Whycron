/**
 * Frontend analytics — Sentry + PostHog initialization and a tiny
 * `track()` wrapper.
 *
 * Both providers are no-ops when their respective env vars are missing,
 * so this file is safe to call from a self-host build that has neither
 * configured. Errors during init never crash the app.
 *
 * What we capture:
 * - Sentry: unhandled JS errors + React error boundaries.
 * - PostHog: page views (autocapture), plus a small list of explicit
 *   funnel events fired from the screens that matter (signup,
 *   monitor_created, upgrade_clicked, ai_explanation_viewed).
 *
 * What we deliberately don't capture:
 * - User-typed monitor names, log excerpts, AI explanation text. Those
 *   stay on our backend.
 * - Anything before the user is signed in beyond the page-view itself.
 */
import * as Sentry from "@sentry/react";
import posthog from "posthog-js";

let _initialized = false;
let _sentryEnabled = false;
let _posthogEnabled = false;

export function initAnalytics(): void {
  if (_initialized) return;
  _initialized = true;

  // ── Sentry ────────────────────────────────────────────────────────────
  const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
  if (sentryDsn) {
    try {
      Sentry.init({
        dsn: sentryDsn,
        environment: import.meta.env.VITE_SENTRY_ENVIRONMENT ?? "development",
        // Conservative defaults — turn up later when we have traffic.
        tracesSampleRate: 0.1,
        replaysSessionSampleRate: 0,
        replaysOnErrorSampleRate: 0.1,
        // Avoid sending PII automatically (email/username get stripped).
        sendDefaultPii: false,
      });
      _sentryEnabled = true;
    } catch (e) {
      // Never let observability init break the app.
      // eslint-disable-next-line no-console
      console.warn("Sentry init failed", e);
    }
  }

  // ── PostHog ───────────────────────────────────────────────────────────
  const phKey = import.meta.env.VITE_POSTHOG_KEY;
  const phHost = import.meta.env.VITE_POSTHOG_HOST ?? "https://us.i.posthog.com";
  if (phKey) {
    try {
      posthog.init(phKey, {
        api_host: phHost,
        person_profiles: "identified_only",
        capture_pageview: true,
        capture_pageleave: true,
        autocapture: true,
        // Don't shadow Sentry — we let Sentry handle error capture.
        disable_session_recording: true,
      });
      _posthogEnabled = true;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("PostHog init failed", e);
    }
  }
}

/** Associate the current PostHog session with the signed-in user. Call
 * once after sign-in completes. */
export function identify(
  userId: string,
  traits: Record<string, unknown> = {},
): void {
  if (!_posthogEnabled) return;
  try {
    posthog.identify(userId, traits);
  } catch {
    /* swallow */
  }
  if (_sentryEnabled) {
    try {
      Sentry.setUser({ id: userId });
    } catch {
      /* swallow */
    }
  }
}

/** Clear identity on sign-out. */
export function resetIdentity(): void {
  if (_posthogEnabled) {
    try {
      posthog.reset();
    } catch {
      /* swallow */
    }
  }
  if (_sentryEnabled) {
    try {
      Sentry.setUser(null);
    } catch {
      /* swallow */
    }
  }
}

/** Explicit funnel event. Use sparingly. */
export function track(
  event: string,
  properties: Record<string, unknown> = {},
): void {
  if (!_posthogEnabled) return;
  try {
    posthog.capture(event, properties);
  } catch {
    /* swallow */
  }
}

/** Sentry-React error boundary, ready to wrap the app root. */
export const ErrorBoundary = Sentry.ErrorBoundary;
