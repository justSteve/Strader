"""Final-fifteen, the spread leg — turning st-ro04's upper bound into a fill. [st-ro04, st-byif]

WHY
    st-ro04 measured what a ~$0.20 0DTE single did in the last fifteen minutes
    and had to report every multiple as a print-to-print UPPER BOUND, because
    the corpus held only `schema: trades` and a spread cannot be inferred from
    prints. That was the one named hole in the study. corpus_pull_opra_quotes.py
    fills it with cbbo-1s NBBO on the same days and the same window.

WHAT
    For each day the premium study chose a leg, this reconstructs that exact
    symbol (day + side + strike is deterministic) and reads the day's quote
    stream to answer three questions the prints could not:

      1. What did it actually cost to get in? Entry at the ASK at 14:45,
         not at the first print.
      2. What could actually be got out? Exit at the BID, and the peak of the
         BID series in the clean window — not the peak of the print series,
         which is a price someone else got.
      3. What is the spread worth as a tax? In dollars and as a fraction of
         the mid, at entry and at the exit moment.

    The headline is `mult_fill` = peak bid / entry ask, beside the study's
    `mult_peak_1459` = peak print / entry print. The gap between them is the
    tax, and on a lottery-shaped trade it is not a rounding error.

    Quotes are one-second consolidated BBO, so a fill inside a second is not
    modelled; this is still an idealisation, just a far tighter one. Crossed or
    zero-bid quotes are dropped and counted rather than silently used.

RUN
    .venv/bin/python3 scripts/measurement/final_fifteen_spread.py [prem.jsonl] [out.jsonl]
"""
from __future__ import annotations

import gzip
import json
import math
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PREM = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-fifteen-premium-2026-08-30.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/measurement/final-fifteen-spread.jsonl"
CLEAN_END_MIN = 14.0    # matches the premium study's 14:59 clean window


def sym_for(day: str, cp: str, k: float) -> str:
    y, m, d = day.split("-")
    return f"SPXW  {y[2:]}{m}{d}{cp}{int(k * 1000):08d}"


def quotes_for(day: str, wanted: set[str]) -> dict[str, list[tuple[str, float, float]]]:
    """symbol -> sorted [(hh:mm:ss, bid, ask)] for the day's quote stream."""
    p = REPO / "data" / "corpus" / day / "databento_opra_quotes.jsonl.gz"
    if not p.exists():
        return {}
    out: dict[str, list[tuple[str, float, float]]] = {}
    with gzip.open(p, "rt") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("data") or {}
            sym = d.get("symbol")
            if sym not in wanted:
                continue
            bid, ask = d.get("bid_px"), d.get("ask_px")
            if bid is None or ask is None:
                continue
            try:
                bid, ask = float(bid), float(ask)
            except (TypeError, ValueError):
                continue
            ts = (r.get("provenance") or {}).get("ts_event") or ""
            out.setdefault(sym, []).append((ts[11:19], bid, ask))
    for v in out.values():
        v.sort()
    return out


def _finite(xs):
    """Drop non-finite values rather than letting one nan poison a median."""
    return [x for x in xs if x is not None and isinstance(x, (int, float)) and math.isfinite(x)]


def _med_pct(spreads, mids):
    vals = _finite([s / m for s, m in zip(spreads, mids) if m])
    return round(st.median(vals), 4) if vals else None


def mins(hms: str, base: str) -> float:
    def s(x):
        return int(x[:2]) * 3600 + int(x[3:5]) * 60 + int(x[6:8])
    return (s(hms) - s(base)) / 60.0


def main() -> int:
    rows = [json.loads(l) for l in open(PREM) if l.strip()]
    ok = [r for r in rows if "skip" not in r]
    written = 0
    no_quotes = 0
    dropped_crossed = 0
    results = []

    with open(OUT, "w") as fout:
        for r in ok:
            day = r["day"]
            legs = {}
            for side, cp in (("call", "C"), ("put", "P")):
                leg = r.get(side) or {}
                if "skip" in leg or leg.get("entry") is None:
                    continue
                legs[sym_for(day, cp, leg["k"])] = (side, leg)
            if not legs:
                continue
            q = quotes_for(day, set(legs))
            if not q:
                no_quotes += 1
                continue
            row = {"day": day}
            for sym, (side, leg) in legs.items():
                series = q.get(sym) or []
                clean = []
                for ts, bid, ask in series:
                    # a NaN quote passes every comparison below and then poisons
                    # max(); drop it here rather than downstream [st-ro04]
                    if not (math.isfinite(bid) and math.isfinite(ask)):
                        dropped_crossed += 1
                        continue
                    if bid <= 0 or ask <= 0 or ask < bid:
                        dropped_crossed += 1
                        continue
                    if mins(ts, series[0][0]) <= CLEAN_END_MIN:
                        clean.append((ts, bid, ask))
                if len(clean) < 5:
                    row[side] = {"skip": "thin-quotes", "n": len(clean)}
                    continue
                base = clean[0][0]
                entry_ask = clean[0][2]
                entry_bid = clean[0][1]
                t_peak_bid, peak_bid, _ = max(clean, key=lambda x: x[1])
                close_bid = clean[-1][1]
                spreads = [(a - b) for _, b, a in clean]
                mids = [(a + b) / 2 for _, b, a in clean]
                entry_spread = entry_ask - entry_bid
                entry_mid = (entry_ask + entry_bid) / 2
                row[side] = {
                    "k": leg["k"], "n_quotes": len(clean),
                    "entry_ask": round(entry_ask, 3), "entry_bid": round(entry_bid, 3),
                    "entry_mid": round(entry_mid, 3),
                    "entry_spread": round(entry_spread, 3),
                    "entry_spread_pct_mid": round(entry_spread / entry_mid, 4) if entry_mid else None,
                    "peak_bid": round(peak_bid, 3),
                    "peak_bid_min": round(mins(t_peak_bid, base), 2),
                    "close_bid": round(close_bid, 3),
                    "median_spread": round(st.median(spreads), 3),
                    "median_spread_pct_mid": _med_pct(spreads, mids),
                    # the number this whole exercise exists for
                    "mult_fill": round(peak_bid / entry_ask, 3) if entry_ask else None,
                    "mult_fill_close": round(close_bid / entry_ask, 3) if entry_ask else None,
                    # the study's print-to-print bound, carried for comparison
                    "mult_print": leg.get("mult_peak_1459"),
                    "print_entry": leg.get("entry"),
                    "print_peak": leg.get("peak_1459"),
                }
            fout.write(json.dumps(row) + "\n")
            results.append(row)
            written += 1

    print(f"wrote {written} day-rows -> {OUT}")
    print(f"days with no quote stream: {no_quotes} · crossed/zero quotes dropped: {dropped_crossed}")

    legs = [(d["day"], s, d[s]) for d in results for s in ("call", "put")
            if s in d and "skip" not in d[s] and d[s].get("mult_fill") is not None]
    if not legs:
        print("no comparable legs yet")
        return 0

    print(f"\n{len(legs)} legs with both a print bound and a quoted fill\n")
    ms = _finite([x[2]["median_spread_pct_mid"] for x in legs])
    es = _finite([x[2]["entry_spread_pct_mid"] for x in legs])
    print(f"spread as a fraction of mid: entry median {100*st.median(es):.1f}%, "
          f"through the window median {100*st.median(ms):.1f}%")
    print(f"entry: ask median ${st.median(x[2]['entry_ask'] for x in legs):.2f} "
          f"vs the study's print entry ${st.median(x[2]['print_entry'] for x in legs):.2f}")
    print()
    fills = _finite([x[2]["mult_fill"] for x in legs])
    prints_ = _finite([x[2]["mult_print"] for x in legs])
    print(f"peak multiple, print-to-print (the bound): median {st.median(prints_):.2f}x")
    print(f"peak multiple, ask-to-bid   (achievable): median {st.median(fills):.2f}x")
    print()
    print("| multiple | print bound | quoted fill |")
    print("|---|---|---|")
    for mult in (2, 3, 5, 10, 20, 50):
        a = sum(1 for x in prints_ if x >= mult)
        b = sum(1 for x in fills if x >= mult)
        print(f"| >= {mult}x | {a} ({100.0*a/len(prints_):.1f}%) | {b} ({100.0*b/len(fills):.1f}%) |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
