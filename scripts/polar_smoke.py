"""One-shot Polar production API smoke test.

Confirms the configured ``POLAR_API_BASE`` + ``POLAR_API_KEY`` pair
authenticates against the live Polar API. Reads ``GET /v1/products/``
and prints a summary of the products returned. Does NOT charge anyone,
does NOT mutate state.

Run with:

    uv run python scripts/polar_smoke.py

Exit codes:
    0   auth works, products fetched
    1   missing config
    2   Polar returned a non-2xx response
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from apps.api.config import settings  # noqa: E402


def main() -> int:
    if not settings.polar_api_key:
        print("POLAR_API_KEY is not set in .env", file=sys.stderr)
        return 1
    if not settings.polar_api_base:
        print("POLAR_API_BASE is not set in .env", file=sys.stderr)
        return 1

    print(f"Polar API base: {settings.polar_api_base}")
    token_prefix = settings.polar_api_key[:14]
    print(f"Polar API token prefix: {token_prefix}...")

    url = f"{settings.polar_api_base.rstrip('/')}/v1/products/"
    headers = {
        "Authorization": f"Bearer {settings.polar_api_key}",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers)

    print(f"GET {url} -> {response.status_code}")
    if response.status_code >= 400:
        print(f"Body: {response.text[:600]}", file=sys.stderr)
        return 2

    body = response.json()
    items = body.get("items", []) or body.get("results", []) or []
    print(f"Products visible to this token: {len(items)}")
    for item in items:
        pid = item.get("id")
        name = item.get("name")
        is_recurring = item.get("is_recurring")
        prices = item.get("prices", [])
        price_summary = "no-price"
        if prices:
            p = prices[0]
            amt = p.get("price_amount") or p.get("amount")
            ccy = p.get("price_currency") or p.get("currency")
            interval = p.get("recurring_interval") or "one-time"
            if amt and ccy:
                price_summary = f"{int(amt) / 100:.2f} {ccy.upper()} / {interval}"
        marker = ""
        if pid == settings.polar_product_pro_id:
            marker = "  <-- matches POLAR_PRODUCT_PRO_ID"
        elif pid == settings.polar_product_team_id:
            marker = "  <-- matches POLAR_PRODUCT_TEAM_ID"
        print(f"  - {pid}  {name!r}  recurring={is_recurring}  {price_summary}{marker}")

    pro_found = any(item.get("id") == settings.polar_product_pro_id for item in items)
    if not settings.polar_product_pro_id:
        print("WARNING: POLAR_PRODUCT_PRO_ID is not set in .env", file=sys.stderr)
    elif not pro_found:
        print(
            f"WARNING: POLAR_PRODUCT_PRO_ID={settings.polar_product_pro_id} "
            "was not returned by this Polar org. Either the UUID is wrong "
            "or the token is scoped to a different org.",
            file=sys.stderr,
        )
    else:
        print("Pro product matches POLAR_PRODUCT_PRO_ID. Ready for checkout.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
