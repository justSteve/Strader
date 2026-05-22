"""GexBot stream pull — one cycle. [st-1yp]

Hits 5 endpoints in sequence respecting the 1 req/sec/metric rate limit:
  /SPX/state/gamma_zero
  /SPX/state/vanna_zero
  /SPX/state/charm_zero
  /SPX/state/delta_zero
  /SPX/classic/gex_zero/majors

Bundles all 5 responses into one record ready to write via writer.
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx

from .writer import utc_now_iso

BASE_URL = "https://api.gex.bot/v2"
USER_AGENT = "Strader-Corpus/0.1 (st-1yp)"
TIMEOUT_S = 5.0
RATE_DELAY_S = 1.1
LOCAL_ADDR_V4 = "0.0.0.0"  # WSL IPv6 broken; see st-rks

ENDPOINTS_DEFAULT = [
    "/SPX/state/gamma_zero",
    "/SPX/state/vanna_zero",
    "/SPX/state/charm_zero",
    "/SPX/state/delta_zero",
    "/SPX/classic/gex_zero/majors",
]


def _load_api_key() -> str:
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    for line in env_path.read_text().splitlines():
        s = line.strip()
        if s.startswith("GEXBOT_API_KEY="):
            return s.partition("=")[2].split("#", 1)[0].strip()
    raise RuntimeError("GEXBOT_API_KEY not found in .env")


def _make_headers(api_key: str) -> dict[str, str]:
    token = api_key if api_key.startswith("gexbot_custom_") else f"gexbot_custom_{api_key}"
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }


def pull_cycle(ticker: str = "SPX") -> dict:
    api_key = _load_api_key()
    headers = _make_headers(api_key)
    ts_pull = utc_now_iso()

    endpoints = [
        ep if "/SPX/" not in ep else ep.replace("/SPX/", f"/{ticker}/")
        for ep in ENDPOINTS_DEFAULT
    ]

    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)
    by_endpoint: dict[str, dict] = {}
    errors: list[str] = []

    with httpx.Client(transport=transport, timeout=TIMEOUT_S) as client:
        for i, ep in enumerate(endpoints):
            url = f"{BASE_URL}{ep}"
            try:
                resp = client.get(url, headers=headers)
                if resp.status_code >= 400:
                    body_text = resp.text[:300]
                    errors.append(f"{ep} HTTP {resp.status_code}: {body_text}")
                    by_endpoint[ep] = {"status_code": resp.status_code, "error_body": body_text}
                else:
                    by_endpoint[ep] = resp.json()
            except httpx.HTTPError as e:
                errors.append(f"{ep} transport: {type(e).__name__}: {e}")
                by_endpoint[ep] = {"transport_error": f"{type(e).__name__}: {e}"}
            if i < len(endpoints) - 1:
                time.sleep(RATE_DELAY_S)

    gamma_zero = by_endpoint.get(f"/{ticker}/state/gamma_zero", {})
    summary = {
        "ts_response_gamma_zero": gamma_zero.get("timestamp"),
        "spot_at_gamma_zero": gamma_zero.get("spot"),
        "major_positive": gamma_zero.get("major_positive"),
        "major_negative": gamma_zero.get("major_negative"),
        "major_long_gamma": gamma_zero.get("major_long_gamma"),
        "major_short_gamma": gamma_zero.get("major_short_gamma"),
        "min_dte": gamma_zero.get("min_dte"),
        "sec_min_dte": gamma_zero.get("sec_min_dte"),
    }

    return {
        "ts_pull_utc": ts_pull,
        "stream": "gexbot",
        "provenance": {
            "endpoints": endpoints,
            "ticker": ticker,
            "base_url": BASE_URL,
        },
        "data": {
            "summary": summary,
            "responses": by_endpoint,
        },
        "errors": errors,
    }
