#!/usr/bin/env python3
"""Ask the GexBot API which tier we actually hold, right now. [st-x3tx]

The registry's DATED section records what Steve reported from the portal; this
asks the endpoints instead. It exists because the two disagreed: Steve confirmed
2026-08-30 that Quant access runs THROUGH 2026-09-06, and on 2026-09-05 he gave
the monthly reset as the 5TH — which would make the 5th the period end, since
the Quant month started 2026-08-05 PM. Reasoning could not settle that. A GET
could, and did: at 2026-09-05 09:51 CDT both Quant-only routes still answered
200, so the reset day is a BILLING boundary and not an access boundary.

Run it whenever a tier claim needs to be a measurement:

    .venv/bin/python3 scripts/gexbot_tier_boundary_probe.py

Reads only. /hist is asked for a date already on disk, so a 200 costs a signed
blob URL that is printed and discarded — nothing is written, nothing downloaded.
Four requests at the 1 req/sec spec limit, so it takes about four seconds.

Exit codes:
    0  the Quant-only routes answered — Quant entitlement is live
    1  they did not — read the bodies; that is the denial shape st-x3tx wants
       for config/entitlements.yaml's gexbot_orderflow_1s ok_values
    2  the probe itself failed (no key, transport dead) — says nothing about tier
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from strader.settings import load_gexbot  # noqa: E402

BASE_URL = "https://api.gex.bot/v2"
USER_AGENT = "Strader-TierProbe/0.1 (st-x3tx)"
RATE_DELAY_S = 1.1
LOCAL_ADDR_V4 = "0.0.0.0"  # WSL IPv6 broken; see st-rks
CENTRAL = ZoneInfo("America/Chicago")

#: (label, path, params, quant_only). The State legs are not filler — if every
#: route fails, the key or the network is the story, not the tier.
CHECKS = (
    ("QUANT-only  /hist 2026-09-04", "/hist/SPX/state/gamma_zero/2026-09-04",
     {"noredirect": "1"}, True),
    ("QUANT-only  /orderflow", "/SPX/orderflow/orderflow", None, True),
    ("STATE keeps /state/gamma_zero", "/SPX/state/gamma_zero", None, False),
    ("STATE keeps /classic majors", "/SPX/classic/gex_zero/majors", None, False),
)


def main() -> int:
    try:
        key = load_gexbot(REPO / ".env")["GEXBOT_API_KEY"]
    except Exception as e:                                   # noqa: BLE001
        print(f"[tier-probe] cannot load GEXBOT_API_KEY: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    token = key if key.startswith("gexbot_custom_") else f"gexbot_custom_{key}"
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT,
               "Accept": "application/json"}

    stamp = datetime.now(CENTRAL).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"GexBot tier boundary — measured {stamp}\n")

    quant_live: list[bool] = []
    reached_anything = False
    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)
    with httpx.Client(transport=transport, timeout=httpx.Timeout(20.0)) as client:
        for i, (label, path, params, quant_only) in enumerate(CHECKS):
            try:
                r = client.get(BASE_URL + path, params=params, headers=headers)
                reached_anything = True
                body = r.text[:110].replace("\n", " ")
                print(f"  {label:32s} HTTP {r.status_code}  {body}")
                if quant_only:
                    quant_live.append(r.status_code == 200)
            except httpx.HTTPError as e:
                print(f"  {label:32s} TRANSPORT {type(e).__name__}: {e}")
                if quant_only:
                    quant_live.append(False)
            if i < len(CHECKS) - 1:
                time.sleep(RATE_DELAY_S)

    if not reached_anything:
        print("\nEvery request failed at the transport. This says nothing about "
              "the tier — the network or the key is the story.", file=sys.stderr)
        return 2

    print()
    if all(quant_live):
        print("QUANT IS LIVE — both Quant-only routes answered 200.")
        return 0
    if any(quant_live):
        print("SPLIT — one Quant-only route answered and one did not. Do not "
              "call this a tier drop until a second run agrees; the API has "
              "expressed throttling as 403 before (st-ox9x).")
        return 1
    print("QUANT IS GONE — neither Quant-only route answered. The bodies above "
          "are the denial shape; record them on st-x3tx and set "
          "config/entitlements.yaml gexbot_orderflow_1s ok_values from them.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
