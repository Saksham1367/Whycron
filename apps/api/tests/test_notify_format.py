"""Alert content rendering tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.api.models import AIExplanation, Monitor, Run
from apps.api.services.notify.format import render_alert


def _make_monitor() -> Monitor:
    return Monitor(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Nightly PostgreSQL Backup",
        ping_token="wcr_test",
        schedule_type="cron",
        schedule_value="0 2 * * *",
        timezone="UTC",
        grace_period_seconds=60,
    )


def _make_run(state: str = "failed", **kwargs) -> Run:
    return Run(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        monitor_id=uuid.uuid4(),
        state=state,
        started_at=kwargs.get("started_at"),
        ended_at=kwargs.get("ended_at"),
        duration_ms=kwargs.get("duration_ms"),
        exit_code=kwargs.get("exit_code"),
        created_at=kwargs.get("created_at", datetime(2026, 5, 11, 2, 2, 0, tzinfo=timezone.utc)),
    )


def _make_explanation(**kwargs) -> AIExplanation:
    return AIExplanation(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        prompt_version="v1",
        model="claude-haiku-4-5-20251001",
        root_cause=kwargs.get(
            "root_cause",
            "Job failed because pg_dump ran out of disk space.",
        ),
        explanation=kwargs.get(
            "explanation",
            "The backup volume hit 100% capacity before the archive could finish writing.",
        ),
        suggested_fix=kwargs.get(
            "suggested_fix", "Rotate old backups or expand the volume."
        ),
        confidence=kwargs.get("confidence", "high"),
        input_tokens=512,
        output_tokens=180,
        cost_usd_micro=1432,
    )


def test_subject_starts_with_prefix() -> None:
    rendered = render_alert(
        monitor=_make_monitor(), run=_make_run(), explanation=None
    )
    assert rendered.subject.startswith("[Whycron] ")


def test_subject_uses_root_cause_first_sentence_when_explanation_present() -> None:
    rendered = render_alert(
        monitor=_make_monitor(),
        run=_make_run(),
        explanation=_make_explanation(),
    )
    assert "pg_dump" in rendered.subject
    assert "ran out of disk space" in rendered.subject


def test_text_body_includes_metadata() -> None:
    rendered = render_alert(
        monitor=_make_monitor(),
        run=_make_run(exit_code=1, duration_ms=5000),
        explanation=_make_explanation(),
    )
    assert "Nightly PostgreSQL Backup" in rendered.text_body
    assert "0 2 * * *" in rendered.text_body
    assert "Exit code: 1" in rendered.text_body
    assert "5000" in rendered.text_body


def test_text_body_three_paragraph_structure() -> None:
    rendered = render_alert(
        monitor=_make_monitor(),
        run=_make_run(),
        explanation=_make_explanation(),
    )
    assert "Root cause." in rendered.text_body
    assert "Explanation." in rendered.text_body
    assert "Suggested fix." in rendered.text_body
    assert "Confidence: high" in rendered.text_body


def test_text_body_handles_missing_explanation() -> None:
    rendered = render_alert(
        monitor=_make_monitor(), run=_make_run(), explanation=None
    )
    assert "AI explanation pending" in rendered.text_body


def test_html_escapes_user_content() -> None:
    monitor = _make_monitor()
    monitor.name = "<script>alert(1)</script>"
    rendered = render_alert(monitor=monitor, run=_make_run(), explanation=None)
    assert "<script>alert(1)</script>" not in rendered.html_body
    assert "&lt;script&gt;" in rendered.html_body


def test_subject_for_missed_run_uses_state_label() -> None:
    rendered = render_alert(
        monitor=_make_monitor(),
        run=_make_run(state="missed"),
        explanation=None,
    )
    assert "missed" in rendered.subject.lower()


def test_html_body_has_basic_structure() -> None:
    rendered = render_alert(
        monitor=_make_monitor(),
        run=_make_run(),
        explanation=_make_explanation(),
    )
    assert "<html" in rendered.html_body.lower()
    assert "</html>" in rendered.html_body.lower()
    assert "background:#10131a" in rendered.html_body  # design system token
