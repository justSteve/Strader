#!/usr/bin/env python3
"""How much price moves per contract of order flow, by time of day, on our own
recorded MBP-1 days. [co-qp8cn]

The absorption survey (COO desk, 2026-09-22) found the literature's answer to
"expected move for this much flow": Cont, Kukanov and Stoikov (2014) regress
the mid-price change per bin on the order-flow imbalance (OFI) at the best
quotes, and find the slope β is proportional to one over the average best-
quote depth, re-estimated every half hour. Takahashi (2025) reproduces it on
ES: depth rises into the last minutes and impact per contract falls.

This script measures the same quantities on our days so the new absorption
detector can scale to them rather than to a fixed contract count:

  per 10-second bin:  OFI (CKS definition from every best-quote update),
                      TI (signed aggressor volume, buys positive),
                      ΔP (mid change in ticks), AD (mean best depth, one side)
  per 15-minute interval:  β_OFI and β_TI (OLS slopes of ΔP on OFI and on TI,
                      through the origin), R² of each, mean AD, and
                      c = β_OFI × AD (CKS: β ≈ c / AD, so c should be roughly
                      constant across the day if the law holds here)

Writes one row per (day, interval) to data/measurement/impact-by-interval.jsonl
and prints the cross-day medians by interval of day.

Usage:
    .venv/bin/python scripts/measurement/impact_by_interval.py             # every day
    .venv/bin/python scripts/measurement/impact_by_interval.py --date 2026-09-18
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from market.orderflow.quotes import (  # noqa: E402
    mbp1_day_path, mbp1_raw_segments, read_mbp1_day, read_mbp1_raw_segment,
)
from market.signals.orderflow_config import TICK  # noqa: E402

logger = logging.getLogger("impact_by_interval")
CORPUS_ROOT = REPO / "data" / "corpus"
DEFAULT_OUT = REPO / "data" / "measurement" / "impact-by-interval.jsonl"

BIN_S = 10
INTERVAL_MIN = 15
RTH_OPEN = _time(8, 30)
RTH_CLOSE = _time(15, 0)


def ofi_step(prev, cur) -> int:
    """CKS e_n for one best-quote update: positive when the bid side gains or
    the ask side loses standing size, negative the other way."""
    pb, pa, qb, qa = prev
    cb, ca, cqb, cqa = cur
    e = 0
    if pb is not None and cb is not None:
        if cb >= pb:
            e += cqb
        if cb <= pb:
            e -= qb
    if pa is not None and ca is not None:
        if ca <= pa:
            e -= cqa
        if ca >= pa:
            e += qa
    return e


def bins_for_day(events) -> list[dict]:
    """Fold a day's book events into 10-second bins inside RTH."""
    bins: list[dict] = []
    cur = None
    prev_q = None
    last_mid = None
    for e in events:
        t = e.ts.time()
        if not (RTH_OPEN <= t < RTH_CLOSE):
            continue
        q = (e.bid_px, e.ask_px, e.bid_sz or 0, e.ask_sz or 0)
        mid = None if e.bid_px is None or e.ask_px is None else (e.bid_px + e.ask_px) / 2
        key = e.ts.replace(second=(e.ts.second // BIN_S) * BIN_S, microsecond=0)
        if cur is None or cur["ts"] != key:
            if cur is not None:
                cur["dp_ticks"] = 0 if cur["mid_end"] is None or cur["mid_start"] is None \
                    else round((cur["mid_end"] - cur["mid_start"]) / TICK)
                bins.append(cur)
            cur = {"ts": key, "ofi": 0, "ti": 0, "vol": 0, "n": 0, "depth_sum": 0,
                   "mid_start": last_mid, "mid_end": None}
        if prev_q is not None:
            cur["ofi"] += ofi_step(prev_q, q)
        if e.action == "T" and e.size and e.side in ("B", "A"):
            cur["ti"] += e.size if e.side == "B" else -e.size
            cur["vol"] += e.size
        cur["n"] += 1
        cur["depth_sum"] += (q[2] + q[3]) / 2
        if mid is not None:
            cur["mid_end"] = mid
            last_mid = mid
            if cur["mid_start"] is None:
                cur["mid_start"] = mid
        prev_q = q
    if cur is not None:
        cur["dp_ticks"] = 0 if cur["mid_end"] is None or cur["mid_start"] is None \
            else round((cur["mid_end"] - cur["mid_start"]) / TICK)
        bins.append(cur)
    return bins


def slope_through_origin(xs, ys) -> tuple[float | None, float | None]:
    sxx = sum(x * x for x in xs)
    if sxx == 0:
        return None, None
    b = sum(x * y for x, y in zip(xs, ys)) / sxx
    ss_res = sum((y - b * x) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum(y * y for y in ys)
    r2 = None if ss_tot == 0 else 1 - ss_res / ss_tot
    return b, r2


def intervals_for_day(day_iso: str, bins: list[dict]) -> list[dict]:
    rows = []
    by_iv: dict[str, list[dict]] = {}
    for b in bins:
        m = (b["ts"].hour * 60 + b["ts"].minute) // INTERVAL_MIN * INTERVAL_MIN
        key = f"{m // 60:02d}:{m % 60:02d}"
        by_iv.setdefault(key, []).append(b)
    for key, bs in sorted(by_iv.items()):
        xs_ofi = [b["ofi"] for b in bs]
        xs_ti = [b["ti"] for b in bs]
        ys = [b["dp_ticks"] for b in bs]
        depth = [b["depth_sum"] / b["n"] for b in bs if b["n"]]
        ad = st.mean(depth) if depth else None
        b_ofi, r2_ofi = slope_through_origin(xs_ofi, ys)
        b_ti, r2_ti = slope_through_origin(xs_ti, ys)
        rows.append({
            "date": day_iso, "interval": key, "bins": len(bs),
            "volume": sum(b["vol"] for b in bs),
            "avg_depth": None if ad is None else round(ad, 1),
            "abs_dp_mean": round(st.mean(abs(y) for y in ys), 3) if ys else None,
            "abs_ti_mean": round(st.mean(abs(x) for x in xs_ti), 1) if xs_ti else None,
            "beta_ofi_ticks_per_contract": None if b_ofi is None else round(b_ofi, 6),
            "r2_ofi": None if r2_ofi is None else round(r2_ofi, 3),
            "beta_ti_ticks_per_contract": None if b_ti is None else round(b_ti, 6),
            "r2_ti": None if r2_ti is None else round(r2_ti, 3),
            "c_ofi": None if (b_ofi is None or ad is None) else round(b_ofi * ad, 4),
        })
    return rows


def events_for_day(day: _date):
    segs = mbp1_raw_segments(day)
    if segs:
        for seg in segs:
            try:
                yield from read_mbp1_raw_segment(seg)
            except Exception as exc:  # a segment broken part-way keeps what it had
                logger.warning("%s %s unreadable: %s", day, seg.name, exc)
        return
    plain = mbp1_day_path(day)
    for p in (plain.with_name(plain.name + ".gz"), plain):
        if p.exists():
            yield from read_mbp1_day(p)
            return


def measure_day(day_iso: str) -> list[dict]:
    day = _date.fromisoformat(day_iso)
    try:
        bins = bins_for_day(events_for_day(day))
    except Exception as exc:
        logger.exception("%s failed", day_iso)
        return [{"date": day_iso, "error": f"{type(exc).__name__}: {exc}"}]
    if not any(b["vol"] for b in bins):
        return [{"date": day_iso, "error": "no RTH trades in the book stream"}]
    return intervals_for_day(day_iso, bins)


def candidate_days(start, end) -> list[str]:
    out = []
    today = _date.today()
    for p in sorted(CORPUS_ROOT.iterdir()):
        try:
            d = _date.fromisoformat(p.name)
        except ValueError:
            continue
        if d >= today or (start and d < start) or (end and d > end):
            continue
        plain = mbp1_day_path(d)
        if mbp1_raw_segments(d) or plain.exists() or plain.with_name(plain.name + ".gz").exists():
            out.append(p.name)
    return out


def summarize(rows: list[dict]) -> None:
    # an interval with under half its bins or no trade is a capture gap, not a
    # measurement (09-18's 08:30 interval: 4 bins, the roll-day reconnect)
    ok = [r for r in rows if "error" not in r and r["avg_depth"] and r["volume"]
          and r["bins"] >= (INTERVAL_MIN * 60 // BIN_S) // 2]
    by_iv: dict[str, list[dict]] = {}
    for r in ok:
        by_iv.setdefault(r["interval"], []).append(r)
    days = len({r["date"] for r in ok})
    print(f"# impact by 15-minute interval of day — medians across {days} days, RTH, "
          f"{BIN_S}-second bins")
    print(f"{'interval':9s} {'days':>4s} {'depth':>7s} {'|ΔP| tk':>8s} {'|TI|':>7s} "
          f"{'β_OFI':>9s} {'R²':>5s} {'β_TI':>9s} {'R²':>5s} {'c=β·D':>7s}")
    for key, rs in sorted(by_iv.items()):
        def med(f):
            vals = [r[f] for r in rs if r[f] is not None]
            return st.median(vals) if vals else float("nan")
        print(f"{key:9s} {len(rs):>4d} {med('avg_depth'):>7.0f} {med('abs_dp_mean'):>8.2f} "
              f"{med('abs_ti_mean'):>7.0f} {med('beta_ofi_ticks_per_contract'):>9.5f} "
              f"{med('r2_ofi'):>5.2f} {med('beta_ti_ticks_per_contract'):>9.5f} "
              f"{med('r2_ti'):>5.2f} {med('c_ofi'):>7.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Price impact per contract by interval of day")
    ap.add_argument("--date")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    days = [args.date] if args.date else candidate_days(
        _date.fromisoformat(args.start) if args.start else None,
        _date.fromisoformat(args.end) if args.end else None)
    rows: list[dict] = []
    if args.jobs <= 1 or len(days) == 1:
        for d in days:
            rows += measure_day(d)
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futs = {pool.submit(measure_day, d): d for d in days}
            for f in as_completed(futs):
                rows += f.result()
                logger.info("%s done", futs[f])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows), encoding="utf-8")
    summarize(rows)
    bad = sorted({r["date"] for r in rows if "error" in r})
    if bad:
        print(f"\nskipped: {', '.join(bad)}")
    logger.info("wrote %s (%d rows)", args.out, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
