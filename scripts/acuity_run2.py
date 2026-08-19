#!/usr/bin/env python3
"""Acuity run 2, LEG B — precision + forward excursion, corpus-wide. [st-n62]

Runs the SetupRecognizer over every corpus day with ES tape, anchored by the
sources trading will actually have (per the bead spec): the day's Mancini
levels (labeled corpus, else the parsed morning letter) plus the prior
session's profile LVNs. For every confirmed recognition, measures pure-code
forward excursion from the confirm-bar close: MFE/MAE over the next 15 and 30
minutes and first-touch resolution at ±TARGET_PTS.

Run 1 (score_recognizer.py, st-3vu) asked "does the machine confirm where
Mancini said an event happened" — sensitivity on showcase days. This run asks
the precision question: of everything the machine confirms, how often does
price then actually go?

Outputs (append-only, one run block per invocation like the replay store):
  data/measurement/acuity-run2-confirmations.jsonl  — one row per confirmation
  data/measurement/acuity-run2-days.jsonl           — one row per day

Usage:  .venv/bin/python scripts/acuity_run2.py            # full corpus
        .venv/bin/python scripts/acuity_run2.py --days 2026-07-22 2026-07-15
        .venv/bin/python scripts/acuity_run2.py --workers 6
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.orderflow.anchors import (                             # noqa: E402
    day_anchors, mancini_kinds_for, mancini_levels_for, mancini_source_for)
from market.orderflow.postmortem import excursion_from_trades   # noqa: E402
from market.orderflow.bars import build_bars                       # noqa: E402
from market.orderflow.profile import build_profile, profile_levels  # noqa: E402
from market.orderflow.recognizer import Anchor, SetupRecognizer    # noqa: E402
from market.orderflow.replay import has_es_day, read_corpus_day   # noqa: E402
from market.orderflow.tpo import (                                 # noqa: E402
    build_tpo, classify_day_type, developing_upto)

logger = logging.getLogger("acuity_run2")

OUT_DIR = REPO_ROOT / "data" / "measurement"
PARSED = REPO_ROOT / "runbook" / "mancini" / "parsed"
TARGET_PTS = 5.0          # first-touch grade: ±5 ES pts from confirm close
WINDOWS_MIN = (15, 30)    # excursion windows
MAX_LVN_ANCHORS = 6       # nearest prior-session LVNs below/above open


def letter_anchors_for(day: _date) -> tuple[list[float], list[Anchor]]:
    """The day's Mancini levels and the anchors they make, by the SAME rule the
    drill, the replay recorder and the live feed use (``anchors.day_anchors``
    with ``mancini_kinds_for``) — minus the two range edges, which this sweep
    has never scored [st-tme: same-anchor rule restored; a parity test pins
    it]. Until 2026-08-19 this script kind-filtered the letter to supports
    while the live path admitted every level as support; now both derive
    support AND resistance anchors from one rule, so the resistance
    (bearish) population enters the measurement for the first time."""
    mancini = mancini_levels_for(day)
    kinds = mancini_kinds_for(day)
    anchors = [a for a in day_anchors(mancini, 0.0, 0.0, kinds)
               if a.kind not in ("range_high", "range_low")]
    return mancini, anchors


def prior_day_lvns(day: _date, open_px: float) -> list[float]:
    """Support-side LVNs from the most recent prior corpus day (≤4 back)."""
    for back in range(1, 5):
        prev = day - timedelta(days=back)
        if has_es_day(prev):
            try:
                trades = read_corpus_day(prev)
            except Exception:
                return []
            if not trades:
                return []
            levels = profile_levels(build_profile(trades), reference_price=open_px)
            lvns = sorted((lv.price for lv in levels
                           if "LVN" in lv.reason and lv.level_type == "support"),
                          reverse=True)
            return list(lvns[:MAX_LVN_ANCHORS])
    return []


def run_day(day: _date) -> dict:
    trades = read_corpus_day(day)
    if not trades:
        return {"day": day.isoformat(), "status": "empty"}
    open_px = trades[0].price
    first_t, last_t = trades[0].ts, trades[-1].ts
    coverage = "rth" if first_t.hour < 9 else "late_day"

    mancini, anchors = letter_anchors_for(day)
    src_label = mancini_source_for(day)
    lvns = prior_day_lvns(day, open_px)

    seen = {(a.price, a.kind) for a in anchors}
    for lv in lvns:
        if (lv, "support") not in seen:
            seen.add((lv, "support"))
            anchors.append(Anchor(lv, "support", f"lvn {lv:g}"))
    if not anchors:
        return {"day": day.isoformat(), "status": "no_anchors",
                "coverage": coverage}

    bars = list(build_bars(iter(trades), n=2000, include_partial=True))
    recs = SetupRecognizer(anchors, mancini_prices=mancini).run(bars)
    confirmed = [r for r in recs if r.state == "confirmed"]
    invalidated = [r for r in recs if r.state == "invalidated"]

    try:
        tpo = build_tpo(trades)
        day_type, _why = classify_day_type(tpo)
    except Exception:
        tpo = None
        day_type = "unknown"

    ts_index = [t.ts for t in trades]
    conf_rows = []
    # cross-check derivation of the recognizer's own fire_index [st-98z]:
    # per-(day,anchor) confirm sequence, counted in chronological confirm
    # order. The recognizer's field is authoritative; a mismatch means the
    # two sequences diverged (e.g. anchor-identity vs price keying) — log it.
    # keyed on (price, kind), not price: a Mancini pivot is a support AND a
    # resistance anchor at one price [st-tme], each with its own fire history.
    fire_counts: dict[tuple[float, str], int] = {}
    for r in confirmed:
        import bisect
        fk = (r.anchor_price, r.anchor_kind)
        fire_counts[fk] = fire_counts.get(fk, 0) + 1
        if r.fire_index != fire_counts[fk]:
            logger.warning(
                "fire_index mismatch %s @ %.2f (%s) %s: recognizer=%d derived=%d",
                day.isoformat(), r.anchor_price, r.anchor_kind,
                r.timestamp.strftime("%H:%M"), r.fire_index, fire_counts[fk])
        i = bisect.bisect_left(ts_index, r.timestamp)
        if i >= len(trades):
            continue
        entry = trades[i].price
        sign = 1 if r.bias == "bullish" else -1
        # Non-lookahead day-type call at confirm time [st-98z]: classify from
        # the brackets fully completed BEFORE the confirm bar's half-hour
        # bracket (the in-progress bracket would leak future trades — the
        # profile is built from the whole day's tape). Late-day tapes
        # (coverage == "late_day") have only a sliver of profile; record what
        # the developing classifier actually sees, upto included.
        if tpo is not None:
            dev_upto = developing_upto(tpo, r.timestamp)
            dev_type, _ = classify_day_type(tpo, upto=dev_upto)
        else:
            dev_upto, dev_type = -1, "unknown"
        row = {"day": day.isoformat(), "setup": r.setup, "bias": r.bias,
               "anchor": r.anchor_price, "anchor_kind": r.anchor_kind,
               "anchor_src": ("mancini" if any(a.price == r.anchor_price and a.mancini
                                               for a in anchors) else "lvn"),
               "ct": r.timestamp.strftime("%H:%M"), "hour": r.timestamp.hour,
               "entry": entry, "confidence": r.confidence,
               "fire_index": r.fire_index,
               "day_type": day_type, "developing_day_type": dev_type,
               "dev_upto": dev_upto, "coverage": coverage}
        for w in WINDOWS_MIN:
            mfe, mae, verdict = excursion_from_trades(
                trades, i, entry, sign, r.timestamp + timedelta(minutes=w), target=TARGET_PTS)
            row[f"mfe{w}"] = round(mfe, 2)
            row[f"mae{w}"] = round(mae, 2)
            row[f"verdict{w}"] = verdict
        conf_rows.append(row)

    return {"day": day.isoformat(), "status": "ok", "coverage": coverage,
            "day_type": day_type, "anchor_src": src_label,
            "n_anchors": len(anchors), "n_lvn_anchors": len(lvns),
            "n_resistance_anchors": sum(1 for a in anchors if a.kind == "resistance"),
            "n_trades": len(trades), "n_bars": len(bars),
            "n_emissions": len(recs), "n_confirmed": len(confirmed),
            "n_invalidated": len(invalidated),
            "first_ct": first_t.strftime("%H:%M"),
            "last_ct": last_t.strftime("%H:%M"),
            "confirmations": conf_rows}


def _worker(day_s: str) -> dict:
    try:
        return run_day(_date.fromisoformat(day_s))
    except Exception as exc:  # one bad day must not sink the sweep
        return {"day": day_s, "status": "error", "detail": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Acuity run 2 LEG B sweep [st-n62]")
    ap.add_argument("--days", nargs="*", help="Specific days (default: all with ES tape)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--since", metavar="YYYY-MM-DD",
                    help="Only days >= this ISO date (string compare)")
    ap.add_argument("--until", metavar="YYYY-MM-DD",
                    help="Only days < this ISO date (string compare)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    if args.days:
        days = sorted(args.days)
    else:
        # compacted days are .jsonl.gz [st-itky]; one glob missed them until 08-19
        days = sorted({p.parent.name for p in
                       (REPO_ROOT / "data" / "corpus").glob("*/databento_glbx_es.jsonl*")})
    if args.since:
        days = [d for d in days if d >= args.since]
    if args.until:
        days = [d for d in days if d < args.until]
    print(f"acuity run 2: {len(days)} days, {args.workers} workers")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    days_out = OUT_DIR / "acuity-run2-days.jsonl"
    conf_out = OUT_DIR / "acuity-run2-confirmations.jsonl"

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_worker, d): d for d in days}
        for n, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            if n % 25 == 0 or n == len(days):
                print(f"  {n}/{len(days)} days done")

    results.sort(key=lambda r: r["day"])
    n_conf = 0
    with days_out.open("a", encoding="utf-8") as fd, \
            conf_out.open("a", encoding="utf-8") as fc:  # append-only stores
        for r in results:
            confs = r.pop("confirmations", [])
            fd.write(json.dumps({"run": run_id} | r, separators=(",", ":")) + "\n")
            for c in confs:
                n_conf += 1
                fc.write(json.dumps({"run": run_id} | c, separators=(",", ":")) + "\n")

    ok = [r for r in results if r["status"] == "ok"]
    print(f"run {run_id}: {len(ok)} scored days, {n_conf} confirmations "
          f"-> {days_out.name}, {conf_out.name}")
    for st in ("no_anchors", "empty", "error"):
        n = sum(1 for r in results if r["status"] == st)
        if n:
            print(f"  {st}: {n} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
