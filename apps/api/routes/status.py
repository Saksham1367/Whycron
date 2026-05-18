"""Public status page route.

Unauthenticated. Server-renders an HTML page from the cached snapshot
built by :mod:`apps.api.services.status_page`. No JavaScript required
to render — the page is fully readable even with JS disabled.

Mounted at ``/status/{slug}`` (no ``/api/v1`` prefix on purpose so the
URL stays clean: ``whycron.com/status/acme``). Returns 404 for unknown
slugs.

Security: every value rendered is HTML-escaped via the standard library.
There is no user-supplied free-text in the public output except monitor
names (which the user opted in by flagging the monitor public). We never
expose log excerpts, AI explanations, schedules with secrets, internal
URLs, or any auth metadata.
"""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse

from apps.api.services.status_page import (
    DAY_BUCKETS,
    PublicMonitor,
    StatusSnapshot,
    load_snapshot,
)

router = APIRouter(tags=["status"])

_OVERALL_LABEL = {
    "operational": ("All systems operational", "#2ad39b"),
    "partial_outage": ("Partial degradation", "#f0b452"),
    "major_outage": ("Major outage", "#e7585c"),
}

_STATE_COLORS = {
    "no_data": "#363b49",
    "succeeded": "#2ad39b",
    "healthy": "#2ad39b",
    "late": "#f0b452",
    "missed": "#e7585c",
    "timed_out": "#e7585c",
    "failed": "#e7585c",
    "paused": "#5a6072",
    "unknown": "#5a6072",
    "failing": "#e7585c",
}


@router.get("/status/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def public_status_page(slug: str) -> HTMLResponse:
    snap = await load_snapshot(slug)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status page not found",
        )
    return HTMLResponse(content=_render(snap, slug), status_code=200)


@router.get("/status/{slug}.json", include_in_schema=False)
async def public_status_page_json(slug: str) -> JSONResponse:
    """JSON variant — same snapshot, machine-readable. Same 404 + cache
    semantics. Useful for clients that want to embed status elsewhere."""
    snap = await load_snapshot(slug)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status page not found",
        )
    return JSONResponse(
        content={
            "organization_name": snap.organization_name,
            "headline": snap.headline,
            "overall": snap.overall,
            "generated_at": snap.generated_at,
            "monitors": [
                {
                    "name": m.name,
                    "status": m.status,
                    "schedule": m.schedule_value,
                    "schedule_type": m.schedule_type,
                    "days": [{"date": d.date, "state": d.state} for d in m.days],
                }
                for m in snap.monitors
            ],
        }
    )


# ── HTML rendering ───────────────────────────────────────────────────────────


def _render(snap: StatusSnapshot, slug: str) -> str:
    overall_label, overall_color = _OVERALL_LABEL.get(
        snap.overall, ("Unknown", "#5a6072")
    )

    if snap.monitors:
        monitors_html = "\n".join(_render_monitor(m) for m in snap.monitors)
    else:
        monitors_html = (
            '<div class="wc-empty">No public monitors yet.</div>'
        )

    headline_block = (
        f'<p class="wc-headline">{escape(snap.headline)}</p>'
        if snap.headline
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Status — {escape(snap.organization_name)}</title>
  <meta name="robots" content="index,follow" />
  <style>
    :root {{
      color-scheme: dark;
      --bg: #10131a;
      --surface: #13171f;
      --border: #363b49;
      --text: #e1e2ec;
      --text-soft: #c2c6d6;
      --text-muted: #8f96ad;
      --primary: #4d8eff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 32px 16px 80px;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 16px;
      line-height: 1.55;
    }}
    main {{
      max-width: 760px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 28px;
      text-align: center;
    }}
    .wc-org {{
      font-size: .72rem;
      color: var(--text-muted);
      letter-spacing: .16em;
      text-transform: uppercase;
      font-weight: 700;
      margin: 0 0 8px;
    }}
    h1 {{
      margin: 0 0 14px;
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: -.03em;
    }}
    .wc-status-pill {{
      display: inline-block;
      padding: 10px 18px;
      border-radius: 999px;
      background: rgba(255,255,255,.04);
      border: 1px solid {overall_color};
      color: {overall_color};
      font-weight: 600;
      font-size: .92rem;
    }}
    .wc-headline {{
      color: var(--text-soft);
      margin: 14px 0 0;
      max-width: 580px;
      margin-left: auto;
      margin-right: auto;
    }}
    .wc-monitor {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px 20px;
      margin: 12px 0;
    }}
    .wc-monitor__row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .wc-monitor__name {{
      font-weight: 600;
      font-size: 1.02rem;
    }}
    .wc-monitor__meta {{
      color: var(--text-muted);
      font-size: .82rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    .wc-monitor__state {{
      font-size: .78rem;
      letter-spacing: .08em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .wc-pips {{
      display: flex;
      gap: 3px;
      margin-top: 14px;
      flex-wrap: nowrap;
      overflow-x: auto;
    }}
    .wc-pip {{
      flex: 1 1 auto;
      min-width: 6px;
      height: 22px;
      border-radius: 3px;
    }}
    .wc-pip-row__meta {{
      display: flex;
      justify-content: space-between;
      color: var(--text-muted);
      font-size: .72rem;
      margin-top: 6px;
    }}
    .wc-empty {{
      text-align: center;
      color: var(--text-muted);
      padding: 40px 0;
    }}
    footer {{
      margin-top: 36px;
      text-align: center;
      color: var(--text-muted);
      font-size: .78rem;
    }}
    footer a {{ color: var(--text-muted); }}
    footer a:hover {{ color: var(--text); }}
  </style>
</head>
<body>
<main>
  <header>
    <p class="wc-org">{escape(snap.organization_name)}</p>
    <h1>System status</h1>
    <span class="wc-status-pill">{escape(overall_label)}</span>
    {headline_block}
  </header>
  {monitors_html}
  <footer>
    Last updated {escape(snap.generated_at)} ·
    <a href="/status/{escape(slug)}.json">JSON</a> ·
    Powered by <a href="https://whycron.com">Whycron</a>
  </footer>
</main>
</body>
</html>
"""


def _render_monitor(m: PublicMonitor) -> str:
    state_color = _STATE_COLORS.get(m.status, "#5a6072")
    state_label = m.status.replace("_", " ")

    pips = []
    for bucket in m.days:
        color = _STATE_COLORS.get(bucket.state, "#363b49")
        title = f"{bucket.date}: {bucket.state.replace('_', ' ')}"
        pips.append(
            f'<span class="wc-pip" style="background:{color};" title="{escape(title)}"></span>'
        )

    meta = f"{escape(m.schedule_type)} · {escape(m.schedule_value)}"

    return f"""
  <div class="wc-monitor">
    <div class="wc-monitor__row">
      <span class="wc-monitor__name">{escape(m.name)}</span>
      <span class="wc-monitor__meta">{meta}</span>
      <span class="wc-monitor__state" style="color:{state_color};">{escape(state_label)}</span>
    </div>
    <div class="wc-pips">{"".join(pips)}</div>
    <div class="wc-pip-row__meta">
      <span>{DAY_BUCKETS} days ago</span>
      <span>Today</span>
    </div>
  </div>"""
