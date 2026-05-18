import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { api, ApiError } from "@/lib/api";

/**
 * Blocking modal shown over the dashboard whenever the signed-in user
 * has not accepted the current published terms version.
 *
 * The user must check BOTH boxes (privacy + terms) before "Accept and
 * continue" enables. On success, we POST the version they're accepting
 * and call ``onAccepted`` so the AppShell can refresh the account
 * snapshot and hide this modal.
 */
export function TermsAcceptanceModal({
  currentVersion,
  onAccepted,
}: {
  currentVersion: string;
  onAccepted: () => void;
}) {
  const [acceptedPrivacy, setAcceptedPrivacy] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = acceptedPrivacy && acceptedTerms && !busy;

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await api.acceptTerms(currentVersion);
      onAccepted();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not record acceptance.";
      setError(msg);
      setBusy(false);
    }
  }

  return (
    <div className="wc-tos-backdrop" role="dialog" aria-modal="true">
      <div className="wc-tos-modal">
        <h2>One quick thing before you continue.</h2>
        <p>
          By using Whycron you agree to the Privacy Policy and Terms of
          Service. Tick both boxes to confirm — we record your acceptance
          (timestamp + IP) as a one-time audit trail.
        </p>

        <label className="wc-tos-modal__row">
          <input
            type="checkbox"
            checked={acceptedPrivacy}
            onChange={(e) => setAcceptedPrivacy(e.target.checked)}
          />
          <span>
            I have read and agree to the{" "}
            <Link to="/privacy" target="_blank" rel="noreferrer">
              Privacy Policy
            </Link>
            .
          </span>
        </label>

        <label className="wc-tos-modal__row">
          <input
            type="checkbox"
            checked={acceptedTerms}
            onChange={(e) => setAcceptedTerms(e.target.checked)}
          />
          <span>
            I have read and agree to the{" "}
            <Link to="/terms" target="_blank" rel="noreferrer">
              Terms of Service
            </Link>
            .
          </span>
        </label>

        {error && <div className="wc-tos-modal__error">{error}</div>}

        <div className="wc-tos-modal__actions">
          <Button
            type="button"
            variant="primary"
            icon="check"
            onClick={submit}
            disabled={!ready}
          >
            {busy ? "Saving…" : "Accept and continue"}
          </Button>
        </div>
      </div>
    </div>
  );
}
