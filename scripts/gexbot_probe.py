#!/usr/bin/env python3
"""GexBot API connectivity probe. [st-rks]

Validates that GEXBOT_API_KEY in .env produces a working authenticated
request, and dumps the raw response shape of the endpoints we care about
for the State-tier evaluation. Cheap diagnostic — run once after dropping
the key, confirm the data lands, then move on to building the distillation
layer in market/ingest/gexbot.py.

Per spec (docs/gexbot/gexbot.spec3.yaml):
- Base URL: https://api.gex.bot/v2
- Auth header: Authorization: Bearer gexbot_custom_<your-secret>
- Required headers: User-Agent, Accept
- Rate limit: 1 req/sec per ticker per metric (data updates 1/sec)
- HTTP timeout: <= 1 second per spec guidance
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://api.gex.bot/v2"
USER_AGENT = "Strader-Probe/0.1 (st-rks)"
# Cold-connection timeout. Spec says steady-state polling should run at <= 1s,
# but TLS 1.3 setup + any IPv6/IPv4 fallback eats that on first connect. 5s
# gives the handshake room without masking real outages.
TIMEOUT_S = 5.0
RATE_DELAY_S = 1.1
# WSL on this distro returns ENETUNREACH on IPv6. Binding the local socket to
# the IPv4 any-address forces IPv4-only connections, dodging the broken AAAA
# route. Remove once WSL IPv6 is fixed at the substrate level.
LOCAL_ADDR_V4 = "0.0.0.0"


def load_env() -> dict[str, str]:
    """The GexBot key through the shared loader: ``{"GEXBOT_API_KEY": ...}``, or
    ``{}`` when it is missing or malformed so the caller's existing "no key"
    branch fires. The value lives in the vault file the repo ``.env`` points at
    (strader/config.py, convention 2026-08-25), never in the tree."""
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from strader.config import ConfigError
    from strader.settings import load_gexbot
    try:
        return load_gexbot(ROOT / ".env")
    except ConfigError as e:
        print(f"GEXBOT_API_KEY unavailable: {e}", file=sys.stderr)
        return {}


def make_headers(api_key: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if api_key:
        # Per spec README: the prefix `gexbot_custom_` must precede the secret.
        # If the user dropped the key with the prefix already attached, don't
        # double it.
        token = api_key if api_key.startswith("gexbot_custom_") else f"gexbot_custom_{api_key}"
        headers["Authorization"] = f"Bearer {token}"
    return headers


def probe(client: httpx.Client, path: str, *, authed: bool, api_key: str | None) -> None:
    url = f"{BASE_URL}{path}"
    headers = make_headers(api_key if authed else None)
    label = f"{'AUTH' if authed else 'OPEN'} GET {path}"
    print(f"\n=== {label} ===")
    try:
        resp = client.get(url, headers=headers, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        print(f"  TRANSPORT ERROR: {e}")
        return
    print(f"  status={resp.status_code}  bytes={len(resp.content)}")
    if resp.status_code >= 400:
        try:
            print(f"  body: {resp.json()}")
        except ValueError:
            print(f"  body: {resp.text[:500]}")
        return
    try:
        body = resp.json()
    except ValueError:
        print(f"  body (non-JSON): {resp.text[:500]}")
        return
    pretty = json.dumps(body, indent=2)
    print(pretty if len(pretty) < 2000 else pretty[:2000] + "\n  ...[truncated]")


def main() -> int:
    env = load_env()
    api_key = env.get("GEXBOT_API_KEY")
    if not api_key:
        print("ERROR: GEXBOT_API_KEY not found in .env", file=sys.stderr)
        return 2

    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)
    with httpx.Client(transport=transport) as client:
        # Public, no auth — confirms baseline reachability.
        probe(client, "/tickers", authed=False, api_key=None)
        time.sleep(RATE_DELAY_S)

        # Authenticated, Classic tier — confirms key is valid.
        probe(client, "/SPX/classic/gex_zero", authed=True, api_key=api_key)
        time.sleep(RATE_DELAY_S)

        # Authenticated, State tier — confirms State subscription is active.
        probe(client, "/SPX/state/gamma_zero", authed=True, api_key=api_key)
        time.sleep(RATE_DELAY_S)

        # Authenticated, State majors — the levels we'll likely build on.
        probe(client, "/SPX/state/gamma_zero/majors", authed=True, api_key=api_key)
        time.sleep(RATE_DELAY_S)

        # Authenticated, State vanna 0DTE — the late-day reversal signal.
        probe(client, "/SPX/state/vanna_zero", authed=True, api_key=api_key)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
