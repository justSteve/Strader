"""GexBot stream pull — one cycle. [st-1yp]

Hits 6 endpoints in sequence respecting the 1 req/sec/metric rate limit:
  /SPX/state/gamma_zero
  /SPX/state/vanna_zero
  /SPX/state/charm_zero
  /SPX/state/delta_zero
  /SPX/classic/gex_zero/majors
  /SPX/orderflow/orderflow      (OPTIONAL — Quant/Orderflow tiers only, st-fyey)

Bundles the responses into one record ready to write via writer.

Optional endpoints skip silently on 401/403 (recorded in the response slot,
NOT in errors[]) so the same collector runs correctly at every subscription
tier — a State-tier key must not generate an error per cycle for a leg it
was never entitled to, and the poller's failure back-off must stay meaningful.
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
    "/SPX/orderflow/orderflow",
]

# Endpoints gated behind tiers we may not be subscribed to. 401/403 here is a
# subscription fact, not a failure — recorded in the response slot, kept out
# of errors[]. [st-fyey]
OPTIONAL_ENDPOINTS = {"/SPX/orderflow/orderflow"}


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
                    optional = ENDPOINTS_DEFAULT[i] in OPTIONAL_ENDPOINTS
                    if optional and resp.status_code in (401, 403):
                        by_endpoint[ep] = {"status_code": resp.status_code,
                                           "skipped": "not entitled at current tier"}
                    else:
                        errors.append(f"{ep} HTTP {resp.status_code}: {body_text}")
                        by_endpoint[ep] = {"status_code": resp.status_code, "error_body": body_text}
                else:
                    body = resp.json()
                    # GexBot signals "not subscribed" for the orderflow package
                    # inside an HTTP 200 — same subscription-fact handling.
                    if (ENDPOINTS_DEFAULT[i] in OPTIONAL_ENDPOINTS
                            and isinstance(body, dict) and set(body) == {"error"}):
                        by_endpoint[ep] = {"status_code": 200,
                                           "skipped": body["error"]}
                    else:
                        by_endpoint[ep] = body
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
