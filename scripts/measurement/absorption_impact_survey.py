#!/usr/bin/env python3
"""ImpactAbsorptionTracker over the recorded days: how often it reads, when,
whether the level held, and what price did in the next 30 minutes. [co-qp8cn]

The tracker is run once per day with its floor at zero so every episode is
collected with its expected ticks, hold time, held/broke flag and refill
count; the grid over ABSORPTION_EXPECTED_TICKS_MIN × ABSORPTION_HOLD_MIN_S is
read off that population (the floor and the hold gate only decide emission,
never episode dynamics — same equivalence the fixed-floor survey pins).

Per day and per grid cell: RTH reads, reads in the last ten minutes, held
reads, and for held reads the 30-minute forward result against the corpus
trades (did price trade beyond the defended level on the attacked side, the
same rule absorption_cluster_outcomes.py uses).

Usage:
    .venv/bin/python scripts/measurement/absorption_impact_survey.py
    .venv/bin/python scripts/measurement/absorption_impact_survey.py --date 2026-09-18

Writes data/measurement/absorption-impact-survey.jsonl (one row per day with
every collected episode summarised per cell) and prints the cross-day table.
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as _date, time as _time, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from market.orderflow.absorption_impact import ImpactAbsorptionTracker  # noqa: E402
from market.orderflow.quotes import (  # noqa: E402
    mbp1_day_path, mbp1_raw_segments, read_mbp1_day, read_mbp1_raw_segment,
)
from market.orderflow.replay import read_corpus_day  # noqa: E402

logger = logging.getLogger("absorption_impact_survey")
CORPUS_ROOT = REPO / "data" / "corpus"
DEFAULT_OUT = REPO / "data" / "measurement" / "absorption-impact-survey.jsonl"

RTH_OPEN, RTH_CLOSE, LAST_TEN = _time(8, 30), _time(15, 0), _time(14, 50)
EXPECTED_GRID = (2.0, 3.0, 4.0, 6.0, 8.0)
HOLD_GRID = (0.0, 5.0, 15.0, 30.0)
FORWARD_MIN = 30
THIN_DAYS = {"2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"}   # st-d6k8 late roll


def in_rth(ts) -> bool:
    return RTH_OPEN <= ts.time() < RTH_CLOSE


def streams_for_day(day: _date):
    segs = mbp1_raw_segments(day)
    if segs:
        for seg in segs:
            yield seg.name, read_mbp1_raw_segment(seg)
        return
    plain = mbp1_day_path(day)
    for p in (plain.with_name(plain.name + ".gz"), plain):
        if p.exists():
            yield p.name, read_mbp1_day(p)
            return


def collect(day: _date) -> tuple[list[dict], dict]:
    """Every episode the tracker would consider, with the floor at zero. The
    tracker restarts per raw segment (a reconnect, and on roll day the
    contract). Returns (episodes, facts)."""
    episodes: list[dict] = []
    facts = {"book_events": 0, "trade_events": 0, "unreadable": [], "segments": 0}
    for label, events in streams_for_day(day):
        facts["segments"] += 1
        tracker = ImpactAbsorptionTracker(expected_ticks_min=0.0, hold_min_s=0.0, refill_min=0)
        seen = 0
        try:
            for e in events:
                seen += 1
                if e.action == "T" and e.size:
                    facts["trade_events"] += 1
                for r in tracker.process(e):
                    episodes.append(_row(r, flushed=False))
        except Exception as exc:
            logger.warning("%s %s unreadable after %d events: %s", day, label, seen, exc)
            facts["unreadable"].append({"segment": label, "events_before": seen,
                                        "error": f"{type(exc).__name__}: {exc}"})
        facts["book_events"] += seen
        for r in tracker.flush():
            episodes.append(_row(r, flushed=True))
    return episodes, facts


def _row(r, flushed: bool) -> dict:
    return {"ts": r.timestamp, "side": r.side, "price": r.price, "vol": r.aggressive_vol,
            "expected": r.expected_ticks, "rate": r.impact_ticks_per_contract,
            "held": r.held, "hold_s": r.hold_s, "refills": r.refill_events,
            "disp": r.displacement_ticks, "flushed": flushed}


def excursions(side: str, price: float, start, trades) -> tuple[float, float] | None:
    """(through, away) in points over the next FORWARD_MIN minutes: how far
    price traded THROUGH the level on the attacked side, and how far it went
    AWAY on the defended side. A bid defense: through = price − lowest print
    below it, away = highest print − price. None without trades."""
    end = start + timedelta(minutes=FORWARD_MIN)
    after = [t.price for t in trades if start < t.ts < end]
    if not after:
        return None
    lo, hi = min(after), max(after)
    if side == "bid":
        return round(max(0.0, price - lo), 2), round(max(0.0, hi - price), 2)
    return round(max(0.0, hi - price), 2), round(max(0.0, price - lo), 2)


def forward_result(ep: dict, trades, through_pts: float = 0.0) -> str | None:
    """'broke' if price traded more than `through_pts` beyond the defended
    level on the attacked side within FORWARD_MIN minutes, else 'held'."""
    x = excursions(ep["side"], ep["price"], ep["ts"], trades)
    if x is None:
        return None
    return "broke" if x[0] > through_pts else "held"


def baseline_excursions(trades) -> list[tuple[float, float]]:
    """The same (through, away) for an ordinary moment: every RTH minute, the
    last print before it taken as a bid-side level (the ask-side mirror gives
    the same numbers by symmetry over enough minutes). This is what a held
    read has to beat."""
    out = []
    if not trades:
        return out
    by_min: dict = {}
    for t in trades:
        if in_rth(t.ts):
            by_min[t.ts.replace(second=0, microsecond=0)] = t
    for m, t in sorted(by_min.items()):
        if t.ts.time() >= _time(14, 30):     # keep the full 30 minutes inside RTH
            break
        x = excursions("bid", t.price, t.ts, trades)
        if x is not None:
            out.append(x)
    return out


BREAK_PTS = 1.0   # 'broke' = traded more than this far through the level within 30 min


def summarize_day(day_iso: str, episodes: list[dict], facts: dict, trades) -> dict:
    rth = [e for e in episodes if in_rth(e["ts"]) and not e["flushed"]]
    cells = {}
    for x in EXPECTED_GRID:
        for h in HOLD_GRID:
            sel = [e for e in rth if e["expected"] >= x and e["hold_s"] >= h]
            held = [e for e in sel if e["held"]]
            by_hour: dict[str, int] = {}
            for e in held:
                k = f"{e['ts'].hour:02d}"
                by_hour[k] = by_hour.get(k, 0) + 1
            xs = [excursions(e["side"], e["price"], e["ts"], trades) for e in held] if trades else []
            xs = [v for v in xs if v is not None]
            cells[f"{x:g}/{h:g}"] = {
                "reads": len(sel), "held": len(held),
                "held_last_ten": sum(1 for e in held if e["ts"].time() >= LAST_TEN),
                "held_by_hour": dict(sorted(by_hour.items())),
                "fwd_scored": len(xs),
                "fwd_broke": sum(1 for th, _ in xs if th > BREAK_PTS),
                "fwd_through_pts": [th for th, _ in xs],
                "fwd_away_pts": [aw for _, aw in xs],
                "held_vol_p50": st.median(e["vol"] for e in held) if held else 0,
                "held_hold_s_p50": round(st.median(e["hold_s"] for e in held), 1) if held else 0,
                "held_refills_p50": st.median(e["refills"] for e in held) if held else 0,
            }
    base = baseline_excursions(trades)
    rates = [e["rate"] for e in rth]
    return {"date": day_iso, **facts, "rth_episodes": len(rth),
            "rate_p50": round(st.median(rates), 5) if rates else None,
            "rate_last_ten_p50": round(st.median(e["rate"] for e in rth
                                                 if e["ts"].time() >= LAST_TEN), 5)
            if any(e["ts"].time() >= LAST_TEN for e in rth) else None,
            "baseline_minutes": len(base),
            "baseline_broke": sum(1 for th, _ in base if th > BREAK_PTS),
            "baseline_through_p50": round(st.median(th for th, _ in base), 2) if base else None,
            "baseline_away_p50": round(st.median(aw for _, aw in base), 2) if base else None,
            "cells": cells}


def survey_day(day_iso: str) -> dict:
    day = _date.fromisoformat(day_iso)
    try:
        episodes, facts = collect(day)
    except Exception as exc:
        logger.exception("%s failed", day_iso)
        return {"date": day_iso, "error": f"{type(exc).__name__}: {exc}"}
    if not facts["trade_events"]:
        return {"date": day_iso, "error": "no trade rows in the book stream"}
    try:
        trades = read_corpus_day(day)
    except FileNotFoundError:
        trades = []
    return summarize_day(day_iso, episodes, facts, trades)


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


def print_table(rows: list[dict]) -> None:
    ok = [r for r in rows if "error" not in r and r["date"] not in THIN_DAYS
          and any(c["reads"] for c in r["cells"].values())]
    base_n = sum(r["baseline_minutes"] for r in ok)
    base_broke = sum(r["baseline_broke"] for r in ok)
    print(f"# ImpactAbsorptionTracker over {len(ok)} sessions (thin late-roll days left out)")
    print("cell = expected-ticks floor / minimum hold seconds. reads and held are medians per session; "
          "'held' = level standing when the episode ended.")
    print(f"30-min forward, held reads only: broke = traded more than {BREAK_PTS:g} pt through the level; "
          f"through/away = median points beyond the level / away from it.")
    print(f"BASELINE, an ordinary RTH minute treated as a level: broke {base_broke / base_n:.0%} of "
          f"{base_n:,} minutes; through p50 {st.median(r['baseline_through_p50'] for r in ok):.2f} pt; "
          f"away p50 {st.median(r['baseline_away_p50'] for r in ok):.2f} pt")
    print(f"{'cell':8s} {'reads':>6s} {'held':>6s} {'held<10m':>9s} {'share':>6s} {'scored':>7s} "
          f"{'broke':>6s} {'through':>8s} {'away':>6s} {'vol p50':>8s} {'hold s':>7s} {'refills':>8s}")
    for x in EXPECTED_GRID:
        for h in HOLD_GRID:
            k = f"{x:g}/{h:g}"
            cs = [r["cells"][k] for r in ok]
            held_tot = sum(c["held"] for c in cs)
            l10 = sum(c["held_last_ten"] for c in cs)
            th = [v for c in cs for v in c["fwd_through_pts"]]
            aw = [v for c in cs for v in c["fwd_away_pts"]]
            scored = sum(c["fwd_scored"] for c in cs)
            broke = sum(c["fwd_broke"] for c in cs)
            print(f"{k:8s} {st.median(c['reads'] for c in cs):>6g} {st.median(c['held'] for c in cs):>6g} "
                  f"{l10:>9d} {(l10 / held_tot if held_tot else 0):>6.0%} {scored:>7d} "
                  f"{(broke / scored if scored else 0):>6.0%} "
                  f"{(st.median(th) if th else 0):>8.2f} {(st.median(aw) if aw else 0):>6.2f} "
                  f"{st.median(c['held_vol_p50'] for c in cs):>8g} "
                  f"{st.median(c['held_hold_s_p50'] for c in cs):>7g} "
                  f"{st.median(c['held_refills_p50'] for c in cs):>8g}")
    r50 = [r["rate_p50"] for r in ok if r["rate_p50"]]
    r10 = [r["rate_last_ten_p50"] for r in ok if r["rate_last_ten_p50"]]
    if r50 and r10:
        print(f"\nimpact rate in force at episode end, median ticks/contract: "
              f"all RTH {st.median(r50):.4f}, last ten minutes {st.median(r10):.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Impact-scaled absorption survey")
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
        rows = [survey_day(d) for d in days]
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futs = {pool.submit(survey_day, d): d for d in days}
            for f in as_completed(futs):
                rows.append(f.result())
                logger.info("%s done", futs[f])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, default=str) + "\n" for r in sorted(rows, key=lambda r: r["date"])),
                        encoding="utf-8")
    print_table(rows)
    bad = [r["date"] for r in rows if "error" in r]
    if bad:
        print(f"\nskipped: {', '.join(sorted(bad))}")
    logger.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
