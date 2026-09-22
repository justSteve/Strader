#!/usr/bin/env python3
"""Held absorption reads scored at the horizons a scalp lives on, against the
same per-minute baseline, sliced by the three things Steve named. [co-qp8cn]

Steve, 2026-09-22: the activity he trades happens at a level of interest, in
under a minute, as larger-than-average prints, and the tradeable horizon is
nearer five minutes than thirty. So this pass takes every episode the
ImpactAbsorptionTracker collects (floor at zero, same population as
absorption_impact_survey.py) and, for the ones whose level HELD when the
episode ended, records:

  - what price did in the next 1, 2, 5 and 30 minutes: how far it traded
    THROUGH the level on the attacked side and AWAY on the defended side, and
    whether a scalp from the level would have WON (away reached TARGET_PTS
    before through exceeded STOP_PTS);
  - how far the level sat from the day's anchors: the Mancini levels the
    recognizer carries for the day (``mancini_levels_for``) and the
    developing session high / low as of the moment the defense began (no
    look-ahead: the edge as it stood then);
  - how long the level stood (``hold_s``) and its print evidence: prints,
    largest print, prints at or above the trailing norm × ABSORPTION_BIG_PRINT_MULT.

The BASELINE is every ordinary RTH minute treated as a level, two ways: 'at'
(the minute's last print, price sitting on it) and 'off' (the minute's low or
high, with price already 2-4 ticks off it, which is the state a held read
fires in), each scored as a bid defense and as an ask defense at the same
four horizons, and also restricted to minutes within N ticks of a Mancini
level — so "near an anchor" is not credited for what any minute near an
anchor does. The 'off' form is the fair comparison for a held read.

The grid over expected-ticks floor × maximum hold × anchor distance × largest
print (as a multiple of the trailing norm) is read off the stored episodes at
print time; ``--table-only``
reprints from the jsonl without touching the tape.

Usage:
    .venv/bin/python scripts/measurement/absorption_scalp_survey.py
    .venv/bin/python scripts/measurement/absorption_scalp_survey.py --date 2026-09-18
    .venv/bin/python scripts/measurement/absorption_scalp_survey.py --table-only

Writes data/measurement/absorption-scalp-survey.jsonl (one row per day: every
episode at or above the widest floor, the held ones scored, and the baseline)
and prints the cross-day tables.
"""
from __future__ import annotations

import argparse
import bisect
import json
import logging
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from market.orderflow.absorption_impact import ImpactAbsorptionTracker  # noqa: E402
from market.orderflow.anchors import mancini_levels_for  # noqa: E402
from market.orderflow.quotes import (  # noqa: E402
    mbp1_day_path, mbp1_raw_segments, read_mbp1_day, read_mbp1_raw_segment,
)
from market.orderflow.replay import read_corpus_day  # noqa: E402
from market.signals.orderflow_config import TICK  # noqa: E402

logger = logging.getLogger("absorption_scalp_survey")
CORPUS_ROOT = REPO / "data" / "corpus"
DEFAULT_OUT = REPO / "data" / "measurement" / "absorption-scalp-survey.jsonl"

RTH_OPEN, RTH_CLOSE, LAST_TEN = _time(8, 30), _time(15, 0), _time(14, 50)
HORIZONS_MIN = (1, 2, 5, 30)
STOP_PTS = 1.0                    # 'broke' = traded more than this through the level
TARGET_PTS = 2.0                  # 'win' = price went this far away before it broke
EXPECTED_GRID = (2.0, 3.0, 4.0)
HOLD_MAX_GRID = (15.0, 30.0, 60.0, None)      # seconds; None = any
ANCHOR_GRID = (2, 4, 8, None)                 # ticks from the nearest Mancini level; None = any
PRINT_GRID = (None, 10, 20, 40)              # largest print at least this many × the trailing norm; None = any
THIN_DAYS = {"2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"}   # st-d6k8 late roll
HEADLINE = {"expected": 3.0, "hold_max": 60.0, "anchor": 4, "print_mult": 20}


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


def collect(day: _date, expected_min: float) -> tuple[list[dict], dict]:
    """Every RTH episode at or above ``expected_min`` expected ticks, with the
    floor otherwise at zero. The tracker restarts per raw segment."""
    episodes: list[dict] = []
    facts = {"book_events": 0, "trade_events": 0, "unreadable": [], "segments": 0,
             "rth_episodes": 0}
    for label, events in streams_for_day(day):
        facts["segments"] += 1
        tracker = ImpactAbsorptionTracker(expected_ticks_min=0.0, hold_min_s=0.0,
                                          refill_min=0, big_prints_min=0)
        seen = 0
        try:
            for e in events:
                seen += 1
                if e.action == "T" and e.size:
                    facts["trade_events"] += 1
                for r in tracker.process(e):
                    if in_rth(r.timestamp):
                        facts["rth_episodes"] += 1
                        if r.expected_ticks >= expected_min:
                            episodes.append(_row(r))
        except Exception as exc:
            logger.warning("%s %s unreadable after %d events: %s", day, label, seen, exc)
            facts["unreadable"].append({"segment": label, "events_before": seen,
                                        "error": f"{type(exc).__name__}: {exc}"})
        facts["book_events"] += seen
        tracker.flush()          # end-of-stream episodes are not finished defenses
    return episodes, facts


def _row(r) -> dict:
    return {"ts": r.timestamp, "start_ts": r.start_ts, "side": r.side, "price": r.price,
            "vol": r.aggressive_vol, "expected": r.expected_ticks, "rate": r.impact_ticks_per_contract,
            "held": r.held, "hold_s": r.hold_s, "refills": r.refill_events,
            "disp": r.displacement_ticks,
            "prints": r.prints, "max_print": r.max_print, "big_prints": r.big_prints,
            "print_norm": r.print_norm}


# ── the forward path on a per-second grid ────────────────────────────────────

class SecondPath:
    """Low and high print per second from the cash open to the close.
    ``score`` walks forward from the second AFTER ``ts``; a horizon is scored
    only when its whole window ends by the close, so a read at 14:58 has a
    1-minute result and no 5-minute one, and the baseline is held to the same
    rule. Through, away, broke and win are from the defender's side."""

    def __init__(self, trades, day: _date):
        tz = trades[0].ts.tzinfo if trades else None
        self.t0 = datetime.combine(day, RTH_OPEN, tzinfo=tz)
        self.n = int((datetime.combine(day, RTH_CLOSE, tzinfo=tz) - self.t0).total_seconds())
        self.lo: list[float | None] = [None] * self.n
        self.hi: list[float | None] = [None] * self.n
        for t in trades:
            i = int((t.ts - self.t0).total_seconds())
            if 0 <= i < self.n:
                lo, hi = self.lo[i], self.hi[i]
                if lo is None or t.price < lo:
                    self.lo[i] = t.price
                if hi is None or t.price > hi:
                    self.hi[i] = t.price

    def score(self, side: str, price: float, ts) -> dict[str, list] | None:
        start = int((ts - self.t0).total_seconds()) + 1
        if start < 0 or start >= self.n:
            return None
        marks = {h * 60: str(h) for h in HORIZONS_MIN if start + h * 60 <= self.n}
        if not marks:
            return None
        out: dict[str, list] = {}
        through = away = 0.0
        won = broke = False
        seen = False
        for k in range(start, start + max(marks)):
            lo, hi = self.lo[k], self.hi[k]
            if lo is not None:
                seen = True
                if side == "bid":
                    th, aw = price - lo, hi - price
                else:
                    th, aw = hi - price, price - lo
                # the same second can hold both the target and the stop; the
                # print order inside it is unknown, so a win needs the target
                # to arrive in a second where the stop does not
                if not broke and not won:
                    if th > STOP_PTS:
                        broke = True
                    elif aw >= TARGET_PTS:
                        won = True
                elif not broke and th > STOP_PTS:
                    broke = True
                through = max(through, th)
                away = max(away, aw)
            off = k - start + 1
            if off in marks:
                out[marks[off]] = [round(through, 2), round(away, 2), broke, won]
        return out if seen else None


def developing_edges(trades):
    """Sorted RTH trade times with the running high and low up to each, for
    'where did the day's edges stand when the defense began'."""
    ts, hi, lo = [], [], []
    h = l_ = None
    for t in trades:
        if not in_rth(t.ts):
            continue
        h = t.price if h is None or t.price > h else h
        l_ = t.price if l_ is None or t.price < l_ else l_
        ts.append(t.ts)
        hi.append(h)
        lo.append(l_)
    return ts, hi, lo


def nearest_ticks(price: float, levels: list[float]) -> int | None:
    if not levels:
        return None
    i = bisect.bisect_left(levels, price)
    cands = [levels[j] for j in (i - 1, i) if 0 <= j < len(levels)]
    return min(round(abs(price - c) / TICK) for c in cands)


def edge_ticks(price: float, start_ts, edges) -> int | None:
    ts, hi, lo = edges
    i = bisect.bisect_right(ts, start_ts) - 1
    if i < 0:
        return None
    return min(round(abs(price - hi[i]) / TICK), round(abs(price - lo[i]) / TICK))


BASELINE_OFF_TICKS = (2, 4)   # a held read fires with price 3 ticks off its level (band 2 + 1)


def baseline(trades, path: SecondPath, mancini: list[float]) -> dict:
    """Every RTH minute as a level, two ways, each scored as a bid defense and
    as an ask defense at every horizon:

      at  — the minute's last print is the level and price sits on it;
      off — the minute's low (bid) or high (ask) is the level and price has
            already left it by BASELINE_OFF_TICKS[0]..[1] ticks, which is
            the state a HELD read fires in (its episode closed because the
            top of book left the two-tick band on the defended side, so it
            starts three ticks off). This is the fair one; the bound on the
            far side matters, since a minute that already sits two points
            above its low has met the target before the clock starts.

    Kept per Mancini-distance band so the anchor cells have their own."""
    by_min: dict[datetime, list] = {}
    for t in trades:
        if in_rth(t.ts):
            by_min.setdefault(t.ts.replace(second=0, microsecond=0), []).append(t)
    rows = []
    for m, ts in sorted(by_min.items()):
        last = ts[-1]
        lo = min(t.price for t in ts)
        hi = max(t.price for t in ts)
        for side in ("bid", "ask"):
            sc = path.score(side, last.price, last.ts)
            if sc is not None:
                rows.append({"kind": "at", "ticks": nearest_ticks(last.price, mancini), "fwd": sc})
            level = lo if side == "bid" else hi
            off = round(((last.price - lo) if side == "bid" else (hi - last.price)) / TICK)
            if BASELINE_OFF_TICKS[0] <= off <= BASELINE_OFF_TICKS[1]:
                sc = path.score(side, level, last.ts)
                if sc is not None:
                    rows.append({"kind": "off", "off": off, "ticks": nearest_ticks(level, mancini),
                                 "fwd": sc})
    return {"minutes": len(by_min), "rows": rows}


def survey_day(day_iso: str) -> dict:
    day = _date.fromisoformat(day_iso)
    try:
        episodes, facts = collect(day, min(EXPECTED_GRID))
    except Exception as exc:
        logger.exception("%s failed", day_iso)
        return {"date": day_iso, "error": f"{type(exc).__name__}: {exc}"}
    if not facts["trade_events"]:
        return {"date": day_iso, "error": "no trade rows in the book stream"}
    try:
        trades = read_corpus_day(day)
    except FileNotFoundError:
        trades = []
    if not trades:
        return {"date": day_iso, "error": "no corpus trades to score against"}
    mancini = sorted(mancini_levels_for(day))
    path = SecondPath(trades, day)
    edges = developing_edges(trades)
    for e in episodes:
        e["mancini_ticks"] = nearest_ticks(e["price"], mancini)
        e["edge_ticks"] = edge_ticks(e["price"], e["start_ts"], edges)
        e["fwd"] = path.score(e["side"], e["price"], e["ts"]) if e["held"] else None
    return {"date": day_iso, **facts, "mancini_levels": len(mancini),
            "episodes": episodes, "baseline": baseline(trades, path, mancini)}


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


# ── tables ───────────────────────────────────────────────────────────────────

def _t(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(v)


def print_ratio(e: dict) -> float:
    return e["max_print"] / e["print_norm"] if e["print_norm"] else 0.0


def cell_select(eps: list[dict], expected: float, hold_max, anchor, print_mult) -> list[dict]:
    return [e for e in eps if e["expected"] >= expected
            and (hold_max is None or e["hold_s"] <= hold_max)
            and (anchor is None or (e["mancini_ticks"] is not None and e["mancini_ticks"] <= anchor))
            and (print_mult is None or print_ratio(e) >= print_mult)]


def fwd_stats(scored: list[dict]) -> dict[str, dict]:
    out = {}
    for h in HORIZONS_MIN:
        k = str(h)
        vals = [s[k] for s in scored if s and k in s]
        n = len(vals)
        out[k] = {"n": n,
                  "broke": (sum(1 for v in vals if v[2]) / n) if n else None,
                  "win": (sum(1 for v in vals if v[3]) / n) if n else None,
                  "through": st.median(v[0] for v in vals) if n else None,
                  "away": st.median(v[1] for v in vals) if n else None}
    return out


def _pct(x):
    return "   -" if x is None else f"{x:4.0%}"


def _pts(x):
    return "    -" if x is None else f"{x:5.2f}"


def _hz_cols(stats: dict) -> str:
    return " ".join(f"{stats[str(h)]['n']:>4d} {_pct(stats[str(h)]['broke'])} {_pct(stats[str(h)]['win'])} "
                    f"{_pts(stats[str(h)]['through'])} {_pts(stats[str(h)]['away'])}"
                    for h in HORIZONS_MIN)


def print_tables(rows: list[dict]) -> None:
    ok = [r for r in rows if "error" not in r and r["date"] not in THIN_DAYS]
    eps = [e for r in ok for e in r["episodes"]]
    for e in eps:
        e["ts"] = _t(e["ts"])
    base_rows = [b for r in ok for b in r["baseline"]["rows"]]
    minutes = sum(r["baseline"]["minutes"] for r in ok)
    with_levels = sum(1 for r in ok if r["mancini_levels"])
    hz_hdr = " ".join(f"{'n' + str(h) + 'm':>4s} {'brk':>4s} {'win':>4s} {'thru':>5s} {'away':>5s}"
                      for h in HORIZONS_MIN)

    print(f"# Held absorption reads at scalp horizons, {len(ok)} sessions "
          f"({with_levels} with Mancini levels; thin late-roll days left out)")
    print(f"broke = traded more than {STOP_PTS:g} pt through the level inside the horizon; "
          f"win = went {TARGET_PTS:g} pt away before that; thru/away = median points.")
    print()
    print(f"## Baseline: an ordinary RTH minute as a level, both sides ({minutes:,} minutes)")
    print("'at': price sits on the minute's last print. 'off': the minute's low or high is the level and "
          f"price has already left it by {BASELINE_OFF_TICKS[0]}-{BASELINE_OFF_TICKS[1]} ticks — "
          "the state a held read fires in.")
    held_all = [e for e in eps if e["held"]]
    if held_all:
        disp = [abs(e["disp"]) for e in held_all]
        hold = [e["hold_s"] for e in held_all]
        print(f"held reads at the widest floor: {len(held_all)}; ticks off the level when the read fires "
              f"p50 {st.median(disp):g}, p90 {sorted(disp)[int(0.9 * len(disp))]:g}; hold p50 {st.median(hold):.1f}s, "
              f"under 60 s {sum(1 for h in hold if h <= 60) / len(hold):.0%}, under 15 s "
              f"{sum(1 for h in hold if h <= 15) / len(hold):.0%}; largest print / norm p50 "
              f"{st.median(print_ratio(e) for e in held_all):.0f}x, p10 "
              f"{sorted(print_ratio(e) for e in held_all)[int(0.1 * len(held_all))]:.0f}x")
    print(f"{'minutes':30s} {hz_hdr}")
    for kind in ("at", "off"):
        kr = [b for b in base_rows if b["kind"] == kind]
        for label, sel in ((f"{kind}: all", kr),
                           *[(f"{kind}: within {a} ticks of Mancini",
                              [b for b in kr if b["ticks"] is not None and b["ticks"] <= a])
                             for a in ANCHOR_GRID if a is not None]):
            print(f"{label:30s} {_hz_cols(fwd_stats([b['fwd'] for b in sel]))}")

    for x in EXPECTED_GRID:
        print()
        print(f"## Floor {x:g} expected ticks — held reads by maximum hold, Mancini distance, largest print")
        print(f"{'hold≤':>6s} {'anchor≤':>8s} {'print≥':>7s} {'reads':>6s} {'held':>5s} {'<10m':>5s} {hz_hdr}")
        for hm in HOLD_MAX_GRID:
            for a in ANCHOR_GRID:
                for pm in PRINT_GRID:
                    sel = cell_select(eps, x, hm, a, pm)
                    held = [e for e in sel if e["held"]]
                    l10 = sum(1 for e in held if e["ts"].time() >= LAST_TEN)
                    print(f"{('any' if hm is None else f'{hm:g}s'):>6s} {('any' if a is None else a):>8} "
                          f"{('any' if pm is None else f'{pm}x'):>7s} {len(sel):>6d} {len(held):>5d} {l10:>5d} "
                          f"{_hz_cols(fwd_stats([e['fwd'] for e in held]))}")

    print()
    print("## Held reads at a developing session edge (day high / low as it stood when the defense began)")
    print(f"{'floor':>6s} {'edge≤':>6s} {'hold≤':>6s} {'reads':>6s} {'held':>5s} {hz_hdr}")
    for x in EXPECTED_GRID:
        for a in (0, 2, 4):
            for hm in (60.0, None):
                sel = [e for e in eps if e["expected"] >= x and e["edge_ticks"] is not None
                       and e["edge_ticks"] <= a and (hm is None or e["hold_s"] <= hm)]
                held = [e for e in sel if e["held"]]
                print(f"{x:>6g} {a:>6d} {('any' if hm is None else f'{hm:g}s'):>6s} {len(sel):>6d} {len(held):>5d} "
                      f"{_hz_cols(fwd_stats([e['fwd'] for e in held]))}")

    h = HEADLINE
    sel = cell_select(eps, h["expected"], h["hold_max"], h["anchor"], h["print_mult"])
    held = [e for e in sel if e["held"]]
    print()
    print(f"## Headline cell by hour: floor {h['expected']:g}, hold ≤ {h['hold_max']:g}s, "
          f"within {h['anchor']} ticks of Mancini, largest print ≥ {h['print_mult']}× the norm "
          f"({len(sel)} reads, {len(held)} held, {len(ok)} sessions)")
    print(f"{'hour':>5s} {'reads':>6s} {'held':>5s} {'per session':>12s} {'5-min win':>10s} {'5-min broke':>12s}")
    for hr in range(8, 15):
        rs = [e for e in sel if e["ts"].hour == hr]
        hs = [e for e in held if e["ts"].hour == hr]
        s5 = fwd_stats([e["fwd"] for e in hs])["5"]
        print(f"{hr:>5d} {len(rs):>6d} {len(hs):>5d} {len(rs) / len(ok):>12.1f} {_pct(s5['win']):>10s} {_pct(s5['broke']):>12s}")

    print()
    print("## Cells with at least 30 held reads, ranked by 5-minute win rate")
    ranked = []
    for x in EXPECTED_GRID:
        for hm in HOLD_MAX_GRID:
            for a in ANCHOR_GRID:
                for pm in PRINT_GRID:
                    held = [e for e in cell_select(eps, x, hm, a, pm) if e["held"]]
                    s = fwd_stats([e["fwd"] for e in held])["5"]
                    if s["n"] >= 30:
                        ranked.append((s["win"], s["broke"], s["n"], x, hm, a, pm, s))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    print(f"{'floor':>6s} {'hold≤':>6s} {'anchor≤':>8s} {'print≥':>7s} {'held':>5s} {'5-min win':>10s} {'5-min broke':>12s} {'thru':>5s} {'away':>5s}")
    for win, broke, n, x, hm, a, pm, s in ranked[:12]:
        print(f"{x:>6g} {('any' if hm is None else f'{hm:g}s'):>6s} {('any' if a is None else a):>8} "
              f"{('any' if pm is None else f'{pm}x'):>7s} {n:>5d} "
              f"{_pct(win):>10s} {_pct(broke):>12s} {_pts(s['through'])} {_pts(s['away'])}")
    if not ranked:
        print("(none)")

    bad = [r["date"] for r in rows if "error" in r]
    if bad:
        print(f"\nskipped: {', '.join(sorted(bad))}")


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Absorption reads at scalp horizons")
    ap.add_argument("--date")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--table-only", action="store_true", help="reprint from the jsonl")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.table_only:
        print_tables(load_rows(args.out))
        return 0
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
    print_tables(rows)
    logger.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
