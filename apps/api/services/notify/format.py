"""Render the alert content for a run + optional AI explanation.

Voice follows the design system: direct, technically literate, no marketing
language. Subject starts with ``[Whycron]`` so users can filter, then the
monitor name, then the AI-extracted root cause's first sentence (or the
plain state label if no explanation exists yet).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape

from apps.api.models import AIExplanation, Monitor, Run


@dataclass(frozen=True)
class RenderedAlert:
    subject: str
    text_body: str
    html_body: str


_STATE_LABELS = {
    "failed": "Job failed",
    "missed": "Job missed",
    "timed_out": "Job timed out",
}


def render_alert(
    *,
    monitor: Monitor,
    run: Run,
    explanation: AIExplanation | None,
) -> RenderedAlert:
    state_label = _STATE_LABELS.get(run.state, f"State: {run.state}")

    if explanation:
        first_sentence = explanation.root_cause.split(".")[0].strip() + "."
        subject = f"[Whycron] {monitor.name}: {first_sentence}"
    else:
        subject = f"[Whycron] {monitor.name}: {state_label.lower()}"

    when = run.ended_at or run.started_at or run.created_at
    when_str = (
        when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if isinstance(when, datetime)
        else "(unknown)"
    )

    text_body = _render_text(
        monitor=monitor,
        run=run,
        explanation=explanation,
        state_label=state_label,
        when_str=when_str,
    )
    html_body = _render_html(
        monitor=monitor,
        run=run,
        explanation=explanation,
        state_label=state_label,
        when_str=when_str,
    )
    return RenderedAlert(subject=subject, text_body=text_body, html_body=html_body)


def _render_text(
    *,
    monitor: Monitor,
    run: Run,
    explanation: AIExplanation | None,
    state_label: str,
    when_str: str,
) -> str:
    lines = [
        f"{state_label}: {monitor.name}",
        "",
        f"When: {when_str}",
        f"Schedule: {monitor.schedule_value} ({monitor.timezone})",
    ]
    if run.exit_code is not None:
        lines.append(f"Exit code: {run.exit_code}")
    if run.duration_ms is not None:
        lines.append(f"Duration: {run.duration_ms} ms")

    if explanation:
        lines += [
            "",
            f"Root cause. {explanation.root_cause}",
            "",
            f"Explanation. {explanation.explanation}",
            "",
            f"Suggested fix. {explanation.suggested_fix or '(none)'}",
            "",
            f"Confidence: {explanation.confidence}",
        ]
    else:
        lines += [
            "",
            "AI explanation pending — check the dashboard in a few seconds.",
        ]

    return "\n".join(lines) + "\n"


def _render_html(
    *,
    monitor: Monitor,
    run: Run,
    explanation: AIExplanation | None,
    state_label: str,
    when_str: str,
) -> str:
    # Inline-styled, minimal HTML — email clients strip CSS classes and most
    # external stylesheets. Colors lifted from the Whycron design system.
    name = escape(monitor.name)
    schedule = escape(monitor.schedule_value)
    tz = escape(monitor.timezone)
    when = escape(when_str)
    state = escape(state_label)
    exit_code = "" if run.exit_code is None else escape(str(run.exit_code))
    duration_ms = "" if run.duration_ms is None else f"{run.duration_ms} ms"

    if explanation:
        ai_block = f"""\
<div style="margin-top:24px;padding:16px;border:1px solid rgba(77,142,255,0.36);border-radius:14px;background:rgba(77,142,255,0.06);">
  <p style="margin:0 0 12px;color:#adc6ff;font-weight:700;font-size:0.72rem;letter-spacing:0.16em;text-transform:uppercase;">AI explanation</p>
  <p style="margin:0 0 12px;color:#e1e2ec;"><strong>Root cause.</strong> {escape(explanation.root_cause)}</p>
  <p style="margin:0 0 12px;color:#c2c6d6;"><strong>Explanation.</strong> {escape(explanation.explanation)}</p>
  <p style="margin:0;color:#c2c6d6;"><strong>Suggested fix.</strong> {escape(explanation.suggested_fix or '(none)')}</p>
  <p style="margin:12px 0 0;color:#8f96ad;font-size:0.8rem;">Confidence: {escape(explanation.confidence)}</p>
</div>"""
    else:
        ai_block = (
            '<p style="margin-top:24px;color:#8f96ad;">'
            "AI explanation pending — check the dashboard in a few seconds."
            "</p>"
        )

    meta_rows = [
        ("When", when),
        ("Schedule", f"{schedule} ({tz})"),
    ]
    if exit_code:
        meta_rows.append(("Exit code", exit_code))
    if duration_ms:
        meta_rows.append(("Duration", duration_ms))
    meta_html = "\n".join(
        f'      <tr><td style="padding:4px 16px 4px 0;color:#8f96ad;">{label}</td>'
        f'<td style="padding:4px 0;color:#e1e2ec;font-family:monospace;">{value}</td></tr>'
        for label, value in meta_rows
    )

    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#10131a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#13171f;border:1px solid #363b49;border-radius:14px;padding:24px;">
    <p style="margin:0 0 8px;color:#ff8a8a;font-weight:700;font-size:0.72rem;letter-spacing:0.16em;text-transform:uppercase;">{state}</p>
    <h2 style="margin:0 0 16px;font-size:1.5rem;color:#e1e2ec;letter-spacing:-0.03em;">{name}</h2>
    <table style="border-collapse:collapse;width:100%;font-size:0.875rem;">
{meta_html}
    </table>
    {ai_block}
    <p style="margin-top:24px;color:#8f96ad;font-size:0.8rem;">— Whycron</p>
  </div>
</body></html>"""
