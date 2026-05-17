import { useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { Button } from "@/components/Button";
import { CodeBlock } from "@/components/CodeBlock";
import { Eyebrow } from "@/components/Eyebrow";
import { StatusBadge } from "@/components/StatusBadge";
import { SurfaceCard } from "@/components/SurfaceCard";
import { Topbar } from "@/components/Topbar";
import type { ShellContext } from "@/components/AppShell";
import { api } from "@/lib/api";
import { fmtAbsolute, fmtCostMicroUSD, fmtDuration } from "@/lib/format";
import type { Run } from "@/lib/types";

export function RunDetailScreen() {
  const { id } = useParams<{ id: string }>();
  const { onSignOut } = useOutletContext<ShellContext>();
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedbackPending, setFeedbackPending] = useState(false);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    api
      .getRun(id)
      .then((r) => mounted && setRun(r))
      .catch((e: Error) => mounted && setError(e.message));
    return () => {
      mounted = false;
    };
  }, [id]);

  async function sendFeedback(value: "helpful" | "not_helpful") {
    if (!run) return;
    setFeedbackPending(true);
    try {
      await api.postRunFeedback(run.id, value);
      const fresh = await api.getRun(run.id);
      setRun(fresh);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to record feedback");
    } finally {
      setFeedbackPending(false);
    }
  }

  return (
    <>
      <Topbar
        crumbs={[
          { label: "Failures", to: "/failures" },
          { label: "Run", last: true },
        ]}
        onSignOut={onSignOut}
      />

      {error && <div className="wc-notice">{error}</div>}

      {!run ? (
        <SurfaceCard>
          <p style={{ color: "var(--wc-text-muted)" }}>Loading run…</p>
        </SurfaceCard>
      ) : (
        <div className="wc-form-grid">
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SurfaceCard
              variant={run.state === "failed" ? "critical" : undefined}
            >
              <Eyebrow>Run</Eyebrow>
              <h2
                style={{
                  font: "600 1.4rem var(--wc-font-body)",
                  letterSpacing: "-0.03em",
                  margin: ".3rem 0 .6rem",
                }}
              >
                <StatusBadge status={run.state} />
              </h2>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr",
                  gap: ".4rem 1rem",
                  fontSize: ".88rem",
                }}
              >
                <span style={{ color: "var(--wc-text-muted)" }}>Started</span>
                <span style={{ fontFamily: "var(--wc-font-code)" }}>
                  {fmtAbsolute(run.started_at)}
                </span>
                <span style={{ color: "var(--wc-text-muted)" }}>Ended</span>
                <span style={{ fontFamily: "var(--wc-font-code)" }}>
                  {fmtAbsolute(run.ended_at)}
                </span>
                <span style={{ color: "var(--wc-text-muted)" }}>Duration</span>
                <span>{fmtDuration(run.duration_ms)}</span>
                <span style={{ color: "var(--wc-text-muted)" }}>Exit code</span>
                <span style={{ fontFamily: "var(--wc-font-code)" }}>
                  {run.exit_code ?? "—"}
                </span>
                <span style={{ color: "var(--wc-text-muted)" }}>Signature</span>
                <span
                  style={{
                    fontFamily: "var(--wc-font-code)",
                    fontSize: ".78rem",
                    color: "var(--wc-text-soft)",
                    wordBreak: "break-all",
                  }}
                >
                  {run.failure_signature_hash ?? "—"}
                </span>
              </div>
            </SurfaceCard>

            {run.log_excerpt && (
              <SurfaceCard>
                <Eyebrow>Log excerpt (redacted)</Eyebrow>
                <CodeBlock error={run.state === "failed"}>
                  {run.log_excerpt}
                </CodeBlock>
              </SurfaceCard>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {run.explanation ? (
              <SurfaceCard variant="ai">
                <Eyebrow>AI explanation</Eyebrow>
                <p
                  style={{
                    margin: ".6rem 0 0",
                    color: "var(--wc-text)",
                    fontWeight: 500,
                  }}
                >
                  <strong>Root cause.</strong> {run.explanation.root_cause}
                </p>
                <p style={{ margin: ".6rem 0 0", color: "var(--wc-text-soft)" }}>
                  <strong>Explanation.</strong> {run.explanation.explanation}
                </p>
                {run.explanation.suggested_fix && (
                  <p style={{ margin: ".6rem 0 0", color: "var(--wc-text-soft)" }}>
                    <strong>Suggested fix.</strong>{" "}
                    {run.explanation.suggested_fix}
                  </p>
                )}
                <div
                  style={{
                    marginTop: ".8rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: ".4rem",
                    color: "var(--wc-text-muted)",
                    fontSize: ".82rem",
                  }}
                >
                  <span>Confidence: {run.explanation.confidence}</span>
                  <span>
                    Model: {run.explanation.model} ·{" "}
                    {run.explanation.input_tokens} in /{" "}
                    {run.explanation.output_tokens} out ·{" "}
                    {fmtCostMicroUSD(run.explanation.cost_usd_micro)}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: ".5rem",
                    marginTop: ".8rem",
                    alignItems: "center",
                  }}
                >
                  <span
                    style={{
                      color: "var(--wc-text-muted)",
                      fontSize: ".82rem",
                    }}
                  >
                    Was this helpful?
                  </span>
                  <Button
                    variant={
                      run.explanation.user_feedback === "helpful"
                        ? "primary"
                        : "secondary"
                    }
                    icon="thumb_up"
                    disabled={feedbackPending}
                    onClick={() => sendFeedback("helpful")}
                  >
                    Yes
                  </Button>
                  <Button
                    variant={
                      run.explanation.user_feedback === "not_helpful"
                        ? "primary"
                        : "secondary"
                    }
                    icon="thumb_down"
                    disabled={feedbackPending}
                    onClick={() => sendFeedback("not_helpful")}
                  >
                    No
                  </Button>
                </div>
              </SurfaceCard>
            ) : run.state === "failed" ? (
              <SurfaceCard variant="ai">
                <Eyebrow>AI explanation</Eyebrow>
                <p
                  style={{
                    color: "var(--wc-text-soft)",
                    margin: ".8rem 0 0",
                    fontSize: ".88rem",
                  }}
                >
                  Pending — the worker will analyze this run within seconds.
                  Refresh to check.
                </p>
              </SurfaceCard>
            ) : (
              <SurfaceCard>
                <p
                  style={{
                    color: "var(--wc-text-muted)",
                    margin: 0,
                    fontSize: ".88rem",
                  }}
                >
                  AI explanations run on failed pings only.
                </p>
              </SurfaceCard>
            )}
          </div>
        </div>
      )}
    </>
  );
}
