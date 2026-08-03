#!/usr/bin/env python3
"""Morning flush anatomy + convergence signals — corpus study. [st-gzwb]

Steve's contention (2026-08-03, follow-on to st-ug5): the recent regime of
large, often V-shaped moves inside the first 2 hours of the cash session is
consistent enough to justify chasing the flush more vigorously than
conventional wisdom accepts — enter, cut on the slightest backtest, re-enter
if the flush resumes. This script measures whether the tape supports that.

Window: 08:30-10:30 CT, every corpus day with morning ES tape.

Definitions (window scale — a 3-pt zigzag fragments 50-90-pt morning ranges
into 100+ noise legs, so the structure is measured on the primary move):
  primary move  largest peak-to-trough (or trough-to-peak) travel inside the
                window: max drawdown span vs max drawup span, larger wins
  V-shape       after the primary move's extreme, price retraces >= 50% of
                the primary move before the window ends
  interruption  counter-move >= T pts from the primary move's running
                extreme, measured only inside the primary move's span;
                it "resumes" when a new move-direction extreme prints

Chase simulation (no hindsight): direction is whichever side of the window
open price triggers first at +/- TRIG pts. Enter on trigger; stop S pts
adverse from entry; re-enter when price takes out the pre-stop extreme
("the flush resumes"); campaign ends when price retraces R_END pts from the
campaign extreme without a new extreme (move over) or at window close.
Baselines from the same entry: one-and-done (single position, R_END trailing
exit, no re-entry) and endure (hold to window close). Friction per attempt:
FD0 model, $15 spread + $3 fees at 0.30 delta = 0.6 ES-pt equivalent.

Usage:
    .venv/bin/python3 scripts/measurement/morning_flush_study.py
    .venv/bin/python3 scripts/measurement/morning_flush_study.py --since 2026-07-01

Output: data/measurement/morning_flush_study.json + progress to stderr.
Re-runnable; the output file is regenerated whole each run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from market.orderflow.replay import read_corpus_day  # noqa: E402

CT = ZoneInfo("America/Chicago")
CORPUS = ROOT / "data" / "corpus"
OUT = ROOT / "data" / "measurement" / "morning_flush_study.json"
W_START = time(8, 30)
W_END = time(10, 30)

# interruption thresholds swept across the primary move (ES pts); 1.0 ~ FD0's
# derived stop, coarser values test where noise ends and structure begins
BT_THRESHOLDS = [1.0, 1.5, 2.0, 3.0, 5.0]
# chase-simulation sweep
SIM_TRIGGERS = [5.0, 8.0]          # pts off window open that arm a campaign
SIM_STOPS = [1.0, 2.0, 3.0, 5.0]   # pts adverse from entry
R_END = 8.0                        # campaign-over reversal from extreme
FRICTION_PTS = 0.6                 # per attempt, ES-pt equivalent (FD0 model)


def primary_move(points):
    """Largest signed travel inside the window.

    One pass each way: max drawdown (peak before trough) and max drawup
    (trough before peak), with their span timestamps. Returns the larger as
    dict(dir, size, start_ts, start_p, end_ts, end_p).
    """
    run_max_p, run_max_ts = points[0][1], points[0][0]
    run_min_p, run_min_ts = points[0][1], points[0][0]
    dd = dict(size=0.0)
    du = dict(size=0.0)
    for ts, p in points:
        if p > run_max_p:
            run_max_p, run_max_ts = p, ts
        if p < run_min_p:
            run_min_p, run_min_ts = p, ts
        if run_max_p - p > dd["size"]:
            dd = dict(size=run_max_p - p, start_ts=run_max_ts,
                      start_p=run_max_p, end_ts=ts, end_p=p)
        if p - run_min_p > du["size"]:
            du = dict(size=p - run_min_p, start_ts=run_min_ts,
                      start_p=run_min_p, end_ts=ts, end_p=p)
    best, d = (dd, -1) if dd["size"] >= du["size"] else (du, 1)
    if best["size"] == 0.0:
        return None
    best = dict(best, dir=d, size=round(best["size"], 2))
    return best


def interruptions(points, move, thresholds):
    """Counter-moves >= T from the running extreme, inside the move's span."""
    d = move["dir"]
    seg = [(ts, p) for ts, p in points
           if move["start_ts"] <= ts <= move["end_ts"]]
    out = {T: [] for T in thresholds}
    if not seg:
        return out
    ext_p = seg[0][1]
    state = {T: None for T in thresholds}
    for ts, p in seg:
        if (p - ext_p) * d > 0:
            for T in thresholds:
                bt = state[T]
                if bt is not None:
                    bt["resumed"] = True
                    bt["resume_s"] = (ts - bt["t0"]).total_seconds()
                    out[T].append(bt)
                    state[T] = None
            ext_p = p
            continue
        adverse = (ext_p - p) * d
        for T in thresholds:
            bt = state[T]
            if bt is None and adverse >= T:
                state[T] = dict(t0=ts, depth=adverse, resumed=False,
                                resume_s=None)
            elif bt is not None and adverse > bt["depth"]:
                bt["depth"] = adverse
    for T in thresholds:
        if state[T] is not None:
            out[T].append(state[T])
    return out


def resume_events(points, move, thresholds):
    """Whole-window resume rates — the honest version of `interruptions`.

    Tracks the running extreme in the primary move's direction from the
    move's start to the WINDOW end (not clipped at the move's extreme, which
    would make every event resume by construction). Each counter-move >= T
    is an event; resumed means a new move-direction extreme printed later in
    the window. remaining = extreme-to-final-extreme travel still ahead at
    event start — what a re-entry could still capture.
    """
    d = move["dir"]
    seg = [(ts, p) for ts, p in points if ts >= move["start_ts"]]
    out = {T: [] for T in thresholds}
    if not seg:
        return out
    final_ext = move["end_p"]
    ext_p = seg[0][1]
    state = {T: None for T in thresholds}
    for ts, p in seg:
        if (p - ext_p) * d > 0:
            for T in thresholds:
                bt = state[T]
                if bt is not None:
                    bt["resumed"] = True
                    bt["resume_s"] = (ts - bt["t0"]).total_seconds()
                    out[T].append(bt)
                    state[T] = None
            ext_p = p
            continue
        adverse = (ext_p - p) * d
        for T in thresholds:
            bt = state[T]
            if bt is None and adverse >= T:
                state[T] = dict(t0=ts, depth=adverse, resumed=False,
                                resume_s=None,
                                remaining=round((final_ext - ext_p) * d, 2))
            elif bt is not None and adverse > bt["depth"]:
                bt["depth"] = adverse
    for T in thresholds:
        if state[T] is not None:
            out[T].append(state[T])
    return out


def simulate(points, w_close_p, trig, stop, oracle_dir=None,
             dip_entry=None):
    """Chase campaign; see module docstring for the model.

    oracle_dir: if given, the campaign trades that direction (hindsight upper
    bound isolating cut/re-enter economics from direction-picking); entry
    still waits for the first +/- trig excursion off the open IN that
    direction. If None, direction = whichever side triggers first.

    dip_entry: if set (pts), re-entry after an exit happens when price backs
    off the running extreme by >= dip_entry pts — joining the backtest —
    instead of on the breakout to a new extreme. The stop then sits `stop`
    pts beyond that dip entry, i.e. the wiggle has to EXTEND by `stop` to
    cut you, not merely continue past a breakout fill.
    """
    open_p = points[0][1]
    entry_p = entry_ts = None
    d = 0
    for ts, p in points:
        if p >= open_p + trig and oracle_dir in (None, 1):
            d, entry_p, entry_ts = 1, p, ts
            break
        if p <= open_p - trig and oracle_dir in (None, -1):
            d, entry_p, entry_ts = -1, p, ts
            break
    if d == 0:
        return None
    attempts = []
    in_pos = True
    e_p = entry_p
    camp_ext = entry_p          # campaign extreme (post-entry best)
    stop_level_ext = entry_p    # extreme standing when last exited
    trail_exits = 0
    for ts, p in points:
        if ts < entry_ts:
            continue
        if (p - camp_ext) * d > 0:
            camp_ext = p
        if in_pos:
            if (camp_ext - p) * d >= R_END:
                attempts.append((e_p, p))       # trail exit: move over for now
                in_pos = False
                trail_exits += 1
                stop_level_ext = camp_ext
            elif (e_p - p) * d >= stop:
                attempts.append((e_p, p))       # stop-out; await resumption
                in_pos = False
                stop_level_ext = camp_ext
        else:
            if dip_entry is not None:
                if (stop_level_ext - p) * d >= dip_entry:  # join the backtest
                    in_pos = True
                    e_p = p
                elif (p - stop_level_ext) * d > 0:
                    stop_level_ext = p           # extreme ran on without us
            elif (p - stop_level_ext) * d > 0:   # flush resumed (breakout)
                in_pos = True
                e_p = p
    if in_pos:
        attempts.append((e_p, points[-1][1]))
    chase_pts = sum((x_p - a_p) * d for a_p, x_p in attempts)
    # one-and-done: same entry, R_END trailing exit, no re-entry
    b1 = None
    ext = entry_p
    for ts, p in points:
        if ts < entry_ts:
            continue
        if (p - ext) * d > 0:
            ext = p
        if (ext - p) * d >= R_END:
            b1 = (p - entry_p) * d
            break
    if b1 is None:
        b1 = (points[-1][1] - entry_p) * d
    b2 = (w_close_p - entry_p) * d
    n = len(attempts)
    return dict(dir=d, entry_p=entry_p,
                entry_t=entry_ts.strftime("%H:%M:%S"),
                attempts=n, trail_exits=trail_exits,
                chase_pts=round(chase_pts, 2),
                chase_net=round(chase_pts - FRICTION_PTS * n, 2),
                one_done_pts=round(b1, 2),
                one_done_net=round(b1 - FRICTION_PTS, 2),
                endure_pts=round(b2, 2),
                endure_net=round(b2 - FRICTION_PTS, 2))


def covariates(day, w_trades, w_points):
    """Signals observable at or shortly after the open."""
    cov = {}
    prior = None
    for back in range(1, 6):
        f = CORPUS / (day - timedelta(days=back)).isoformat() / \
            "databento_glbx_es.jsonl"
        if f.exists():
            try:
                pts = read_corpus_day(day - timedelta(days=back))
            except Exception:
                continue
            if pts:
                prior = pts[-1].price
                break
    open_p = w_points[0][1]
    cov["gap_pts"] = round(open_p - prior, 2) if prior is not None else None
    for label, mins in (("f5", 5), ("f15", 15)):
        cut = datetime.combine(day, W_START, CT) + timedelta(minutes=mins)
        seg = [p for ts, p in w_points if ts < cut]
        tr = [t for t in w_trades if t.ts < cut]
        if seg:
            cov[f"{label}_range"] = round(max(seg) - min(seg), 2)
            cov[f"{label}_net"] = round(seg[-1] - seg[0], 2)
            cov[f"{label}_delta"] = sum(t.size if t.side == "B" else -t.size
                                        for t in tr if t.side in "BA")
            cov[f"{label}_vol"] = sum(t.size for t in tr)
    tickf = CORPUS / day.isoformat() / "internals.jsonl"
    if tickf.exists():
        ticks = []
        with tickf.open() as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("provenance", {}).get("symbol") != "$TICK":
                    continue
                hhmm = row["provenance"].get("ts_candle", "")[11:16]
                if "08:30" <= hhmm < "09:00":
                    ticks.append(row["data"])
        if ticks:
            cov["tick_f30_min"] = min(t["low"] for t in ticks)
            cov["tick_f30_max"] = max(t["high"] for t in ticks)
            cov["tick_f30_last"] = ticks[-1]["close"]
    cov["dow"] = day.strftime("%a")
    return cov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, default=None,
                    help="skip corpus days before this date")
    args = ap.parse_args()

    results = []
    skipped = []
    for p in sorted(CORPUS.iterdir()):
        if not p.name.startswith("20") or not (p / "databento_glbx_es.jsonl").exists():
            continue
        try:
            d = date.fromisoformat(p.name)
        except ValueError:
            continue
        if args.since and d < args.since:
            continue
        try:
            trades = read_corpus_day(d)
        except Exception as e:
            skipped.append((d, f"read error: {e}"))
            continue
        w = [t for t in trades if W_START <= t.ts.time() < W_END]
        if not w or w[0].ts.time() > time(8, 35):
            skipped.append((d, "no morning tape"))
            continue
        points = [(t.ts, t.price) for t in w]
        ps = [p_ for _, p_ in points]
        open_p, close_p = ps[0], ps[-1]
        hi, lo = max(ps), min(ps)
        row = dict(date=d.isoformat(), open=open_p, close_1030=close_p,
                   net=round(close_p - open_p, 2), range=round(hi - lo, 2),
                   max_up=round(hi - open_p, 2), max_dn=round(open_p - lo, 2),
                   hi_t=points[ps.index(hi)][0].strftime("%H:%M"),
                   lo_t=points[ps.index(lo)][0].strftime("%H:%M"))
        move = primary_move(points)
        if move:
            row["move"] = dict(dir="up" if move["dir"] == 1 else "dn",
                               size=move["size"],
                               start=move["start_ts"].strftime("%H:%M:%S"),
                               end=move["end_ts"].strftime("%H:%M:%S"),
                               dur_min=round((move["end_ts"] - move["start_ts"])
                                             .total_seconds() / 60, 1))
            after = [(ts, p_) for ts, p_ in points if ts > move["end_ts"]]
            retr = 0.0
            if after:
                if move["dir"] == 1:
                    retr = move["end_p"] - min(p_ for _, p_ in after)
                else:
                    retr = max(p_ for _, p_ in after) - move["end_p"]
            row["v_shape"] = bool(retr >= 0.5 * move["size"])
            row["retrace_pts"] = round(retr, 2)
            row["retrace_frac"] = round(retr / move["size"], 2)
            anat = interruptions(points, move, BT_THRESHOLDS)
            row["interruptions"] = {}
            for T in BT_THRESHOLDS:
                resumed = [b for b in anat[T] if b["resume_s"] is not None]
                med = (sorted(b["resume_s"] for b in resumed)
                       [len(resumed) // 2] if resumed else None)
                row["interruptions"][str(T)] = dict(
                    n=len(anat[T]), resumed=len(resumed),
                    max_depth=round(max((b["depth"] for b in anat[T]),
                                        default=0.0), 2),
                    med_resume_s=round(med, 1) if med is not None else None)
            row["resume_events"] = {
                str(T): [dict(depth=round(b["depth"], 2),
                              resumed=b["resumed"],
                              resume_s=(round(b["resume_s"], 1)
                                        if b["resume_s"] is not None else None),
                              remaining=b["remaining"],
                              t=b["t0"].strftime("%H:%M:%S"))
                         for b in evs]
                for T, evs in resume_events(points, move,
                                            BT_THRESHOLDS).items()}
            row["sim"] = {}
            odir = move["dir"]
            for trig in SIM_TRIGGERS:
                for s in SIM_STOPS:
                    r = simulate(points, close_p, trig, s)
                    if r:
                        row["sim"][f"t{trig:g}_s{s:g}"] = r
                    r2 = simulate(points, close_p, trig, s, oracle_dir=odir)
                    if r2:
                        row["sim"][f"t{trig:g}_s{s:g}_oracle"] = r2
                    for dip in (2.0, 3.0):
                        r3 = simulate(points, close_p, trig, s,
                                      dip_entry=dip)
                        if r3:
                            row["sim"][f"t{trig:g}_s{s:g}_dip{dip:g}"] = r3
        row["cov"] = covariates(d, w, points)
        results.append(row)
        mv = row.get("move", {})
        print(f"{d} ok net={row['net']:+7.2f} range={row['range']:6.2f} "
              f"move={mv.get('size', 0):6.2f} {mv.get('dir', '--')} "
              f"({mv.get('start', '')}→{mv.get('end', '')}) "
              f"v={row.get('v_shape')} retr={row.get('retrace_frac', 0)}",
              file=sys.stderr)
    for d, why in skipped:
        print(f"{d} SKIP {why}", file=sys.stderr)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1))
    print(f"wrote {len(results)} days -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
