"""GexBot 90-day historical backfill. [st-ox9x]

Pulls every package/category for every date in the /hist look-back window
(90 calendar days) and stores the files as received (gzip) under
data/corpus/gexbot-hist/<date>/<package>_<category>.json.gz.

Resumable: existing non-empty files are skipped, so re-running after an
interruption (or at month-end for a final sweep) only fetches what's missing.
A manifest line is appended per attempt to gexbot-hist/manifest.jsonl.

Category roster mirrors the vendor's own downloader (nfa-llc/quant-historical
main.py). A missing file for a weekday is recorded as no-file (holiday or
not-archived), not an error. Orderflow package is attempted and recorded even
if the entitlement is absent — the manifest then shows exactly what the tier
delivered.

Rate limit: 1.1s between API (signed-URL) requests per the 1 req/sec spec;
blob downloads are separate and not API-rate-limited.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

BASE_URL = "https://api.gex.bot/v2"
USER_AGENT = "Strader-Backfill/0.1 (st-ox9x)"
RATE_DELAY_S = 1.1
LOCAL_ADDR_V4 = "0.0.0.0"  # WSL IPv6 broken; see st-rks

COMBOS = (
    [("state", c) for c in (
        "gex_full", "gex_zero", "gex_one",
        "delta_zero", "gamma_zero", "vanna_zero", "charm_zero",
        "delta_one", "gamma_one", "vanna_one", "charm_one")]
    + [("classic", c) for c in ("gex_full", "gex_zero", "gex_one")]
    + [("orderflow", "orderflow")]
)

HIST_ROOT = REPO / "data" / "corpus" / "gexbot-hist"
MANIFEST = HIST_ROOT / "manifest.jsonl"


def _load_api_key() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        line = line.strip()
        if line.startswith("GEXBOT_API_KEY="):
            key = line.partition("=")[2].split("#", 1)[0].strip()
            return key if key.startswith("gexbot_custom_") else f"gexbot_custom_{key}"
    raise RuntimeError("GEXBOT_API_KEY not found in .env")


def manifest_append(entry: dict) -> None:
    HIST_ROOT.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="GexBot /hist backfill")
    ap.add_argument("--ticker", default="SPX")
    ap.add_argument("--days", type=int, default=90,
                    help="Calendar days back from --end (default 90)")
    ap.add_argument("--end", default=None,
                    help="Last date to fetch, YYYY-MM-DD (default: yesterday)")
    args = ap.parse_args()

    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    days = [end - timedelta(days=i) for i in range(args.days)]
    weekdays = [d for d in days if d.weekday() < 5]

    token = _load_api_key()
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT,
               "Content-Type": "application/json"}

    fetched = skipped = nofile = failed = 0
    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)
    with httpx.Client(transport=transport,
                      timeout=httpx.Timeout(30.0, read=240.0)) as client:
        for d in sorted(weekdays):
            day_dir = HIST_ROOT / d.isoformat()
            for package, category in COMBOS:
                out = day_dir / f"{package}_{category}.json.gz"
                if out.exists() and out.stat().st_size > 0:
                    skipped += 1
                    continue
                url = f"{BASE_URL}/hist/{args.ticker}/{package}/{category}/{d.isoformat()}"
                entry = {"date": d.isoformat(), "package": package, "category": category}
                try:
                    # The API sometimes expresses throttling as 403 — identical
                    # body to a real entitlement denial (observed st-ox9x smoke
                    # test: same combo fetched one day, 403 the next). Retry
                    # with backoff before believing a denial.
                    for attempt in range(3):
                        r = client.get(url, params={"noredirect": "1"}, headers=headers)
                        time.sleep(RATE_DELAY_S)
                        if r.status_code == 403 and attempt < 2:
                            time.sleep(15 * (attempt + 1))
                            continue
                        break
                    if r.status_code != 200 or "url" not in r.json():
                        body = r.text[:200]
                        # Distinguish "no archive for this date" from entitlement/errors
                        if "not found" in body.lower() or r.status_code == 404:
                            entry.update(status="no-file", detail=body)
                            nofile += 1
                        elif r.status_code == 403:
                            entry.update(status="denied", http=403, detail=body)
                            failed += 1
                        else:
                            entry.update(status="failed", http=r.status_code, detail=body)
                            failed += 1
                        manifest_append(entry)
                        continue
                    signed = r.json()["url"]
                    blob = client.get(signed, headers={"User-Agent": USER_AGENT})
                    if blob.status_code != 200:
                        entry.update(status="failed", http=blob.status_code,
                                     detail="blob download failed")
                        failed += 1
                        manifest_append(entry)
                        continue
                    day_dir.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(blob.content)
                    entry.update(status="fetched", bytes=len(blob.content))
                    fetched += 1
                    manifest_append(entry)
                except httpx.HTTPError as e:
                    entry.update(status="failed", detail=f"{type(e).__name__}: {e}")
                    failed += 1
                    manifest_append(entry)
            print(f"{d.isoformat()}  done  (totals: {fetched} fetched, {skipped} skipped, "
                  f"{nofile} no-file, {failed} failed)", flush=True)

    print(f"BACKFILL COMPLETE: {fetched} fetched, {skipped} already present, "
          f"{nofile} no-file, {failed} failed", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
