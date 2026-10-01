"""Build ``recorded_2026-09-30.json`` from the corpus. [st-ug1h]

Run once, by hand, from the repo root; the output is committed so the
scenario suite never reads ``data/corpus`` (which is not in git and is
gigabytes):

    python3 tests/execd/scenario/fixtures/build_recorded.py [corpus-root]

(``corpus-root`` defaults to ``data/corpus`` in this checkout; a worktree
has none, so pass the main checkout's.)

What it keeps, and from where:

* **The index path.** ``data/corpus/2026-09-30/databento_glbx_es.jsonl`` —
  the live Databento ES trade stream — reduced to the last trade in each
  second from 13:15:00 to 13:45:00 CT (18:15–18:45 UTC), the half hour
  around the two paper incidents of that day (13:24 and 13:38 CT,
  st-0f5q). SPX is that ES price less ONE basis, the 18:00 UTC Schwab
  pull's ``es_minus_spx_basis`` (one measurement held for the window, not a
  rolling estimator). A second with no trade carries the last price.
* **The option chain.** The same 18:00 UTC Schwab pull's ``chain_window``
  (20 calls, 20 puts, 7660–7755): strike, bid, ask and the chain's own IV
  and delta. The replay prices each contract from its recorded IV as the
  path moves (``tape.OptionModel``); the spreads are the recorded ones.

Nothing else is read. The output is about 60 KB.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DAY = "2026-09-30"
CORPUS = Path(sys.argv[1] if len(sys.argv) > 1 else REPO / "data" / "corpus") / DAY
START = datetime(2026, 9, 30, 18, 15, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 18, 45, tzinfo=timezone.utc)
OUT = Path(__file__).with_name(f"recorded_{DAY}.json")


def main() -> int:
    pulls = [json.loads(line) for line in (CORPUS / "schwab.jsonl").open()]
    pull = next(p for p in pulls if p["ts_pull_utc"] == "2026-09-30T18:00:08Z")
    basis = round(float(pull["data"]["es_minus_spx_basis"]), 2)
    lo, hi = START.isoformat()[:19], END.isoformat()[:19]
    last: dict[int, float] = {}
    with (CORPUS / "databento_glbx_es.jsonl").open() as fh:
        for line in fh:
            if '"ts_event": "2026-09-30T18:' not in line:
                continue
            row = json.loads(line)
            ts = row["provenance"]["ts_event"][:19]
            if not (lo <= ts < hi):
                continue
            sec = int((datetime.fromisoformat(ts + "+00:00") - START).total_seconds())
            last[sec] = float(row["data"]["price"])
    if not last:
        print("no ES trades in the window", file=sys.stderr)
        return 1
    n = int((END - START).total_seconds())
    path: list[float] = []
    price = last[min(last)]
    for s in range(n):
        price = last.get(s, price)
        path.append(round(price - basis, 2))
    chain = [{k: r[k] for k in ("strike", "side", "bid", "ask", "iv", "delta")}
             for r in pull["data"]["chain_window"]]
    OUT.write_text(json.dumps({
        "day": DAY, "start_utc": START.isoformat(), "step_s": 1,
        "source": {"index": f"data/corpus/{DAY}/databento_glbx_es.jsonl (last trade per second)",
                   "basis": f"schwab.jsonl 18:00:08Z es_minus_spx_basis = {basis}",
                   "chain": "schwab.jsonl 18:00:08Z chain_window"},
        "basis": basis, "chain_spx": pull["data"]["spot_spx"],
        "spx": path, "chain": chain,
    }, separators=(",", ":")) + "\n")
    print(f"{OUT.name}: {len(path)} seconds, SPX {min(path)}–{max(path)}, "
          f"{len(last)} seconds traded, basis {basis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
