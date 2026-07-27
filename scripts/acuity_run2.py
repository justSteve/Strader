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

from market.orderflow.anchors import mancini_levels_for            # noqa: E402
from market.orderflow.bars import build_bars                       # noqa: E402
from market.orderflow.profile import build_profile, profile_levels  # noqa: E402
from market.orderflow.recognizer import Anchor, SetupRecognizer    # noqa: E402
from market.orderflow.replay import es_day_path, read_corpus_day   # noqa: E402
from market.orderflow.tpo import build_tpo, classify_day_type      # noqa: E402

logger = logging.getLogger("acuity_run2")

OUT_DIR = REPO_ROOT / "data" / "measurement"
PARSED = REPO_ROOT / "runbook" / "mancini" / "parsed"
TARGET_PTS = 5.0          # first-touch grade: ±5 ES pts from confirm close
WINDOWS_MIN = (15, 30)    # excursion windows
MAX_LVN_ANCHORS = 6       # nearest prior-session LVNs below/above open


def letter_levels_for(day: _date) -> list[float]:
    p = PARSED / f"{day.isoformat()}.json"
    if not p.exists():
        return []
    try:
        j = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return sorted({round(float(l["price"]), 2) for l in j.get("levels", [])
                   if l.get("kind") == "support" and 5000 < float(l["price"]) < 9000})


def prior_day_lvns(day: _date, open_px: float) -> list[float]:
    """Support-side LVNs from the most recent prior corpus day (≤4 back)."""
    for back in range(1, 5):
        prev = day - timedelta(days=back)
        if es_day_path(prev).exists():
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


def _excursion(trades: list, start_i: int, entry: float, sign: int,
               until: datetime) -> tuple[float, float, str]:
    """MFE, MAE (pts) and first-touch verdict from trades[start_i:] until ts."""
    mfe = mae = 0.0
    verdict = "neither"
    for t in trades[start_i:]:
        if t.ts > until:
            break
        ex = sign * (t.price - entry)
        if ex > mfe:
            mfe = ex
        if -ex > mae:
            mae = -ex
        if verdict == "neither":
            if ex >= TARGET_PTS:
                verdict = "win"
            elif ex <= -TARGET_PTS:
                verdict = "loss"
    return mfe, mae, verdict


def run_day(day: _date) -> dict:
    trades = read_corpus_day(day)
    if not trades:
        return {"day": day.isoformat(), "status": "empty"}
    open_px = trades[0].price
    first_t, last_t = trades[0].ts, trades[-1].ts
    coverage = "rth" if first_t.hour < 9 else "late_day"

    mancini = mancini_levels_for(day)
    src_label = "labels"
    if not mancini:
        mancini = letter_levels_for(day)
        src_label = "letter" if mancini else "none"
    lvns = prior_day_lvns(day, open_px)

    anchors, seen = [], set()
    for lv in mancini:
        if lv not in seen:
            seen.add(lv)
            anchors.append(Anchor(lv, "support", f"mancini {lv:g}", mancini=True))
    for lv in lvns:
        if lv not in seen:
            seen.add(lv)
            anchors.append(Anchor(lv, "support", f"lvn {lv:g}"))
    if not anchors:
        return {"day": day.isoformat(), "status": "no_anchors",
                "coverage": coverage}

    bars = list(build_bars(iter(trades), n=2000, include_partial=True))
    recs = SetupRecognizer(anchors, mancini_prices=mancini).run(bars)
    confirmed = [r for r in recs if r.state == "confirmed"]
    invalidated = [r for r in recs if r.state == "invalidated"]

    try:
        day_type, _why = classify_day_type(build_tpo(trades))
    except Exception:
        day_type = "unknown"

    ts_index = [t.ts for t in trades]
    conf_rows = []
    for r in confirmed:
        import bisect
        i = bisect.bisect_left(ts_index, r.timestamp)
        if i >= len(trades):
            continue
        entry = trades[i].price
        sign = 1 if r.bias == "bullish" else -1
        row = {"day": day.isoformat(), "setup": r.setup, "bias": r.bias,
               "anchor": r.anchor_price,
               "anchor_src": ("mancini" if any(a.price == r.anchor_price and a.mancini
                                               for a in anchors) else "lvn"),
               "ct": r.timestamp.strftime("%H:%M"), "hour": r.timestamp.hour,
               "entry": entry, "confidence": r.confidence,
               "day_type": day_type, "coverage": coverage}
        for w in WINDOWS_MIN:
            mfe, mae, verdict = _excursion(
                trades, i, entry, sign, r.timestamp + timedelta(minutes=w))
            row[f"mfe{w}"] = round(mfe, 2)
            row[f"mae{w}"] = round(mae, 2)
            row[f"verdict{w}"] = verdict
        conf_rows.append(row)

    return {"day": day.isoformat(), "status": "ok", "coverage": coverage,
            "day_type": day_type, "anchor_src": src_label,
            "n_anchors": len(anchors), "n_lvn_anchors": len(lvns),
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
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    if args.days:
        days = sorted(args.days)
    else:
        days = sorted(p.parent.name for p in
                      (REPO_ROOT / "data" / "corpus").glob("*/databento_glbx_es.jsonl"))
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
