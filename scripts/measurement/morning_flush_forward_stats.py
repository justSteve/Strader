#!/usr/bin/env python3
"""Forward-looking backtest economics — no terminal-extreme hindsight. [st-kmmg]

Why this script exists. `morning_flush_study.resume_events()` labels each
counter-move with `resumed` and `remaining`, and BOTH are derived from the
primary move's terminal extreme — a quantity nobody standing in the trade can
see. The 2026-08-04 auditor's report (§1.2, §6.2, §6.6) checked all 2,535
stored events and found `resumed == (remaining > 0)` in 2,535 of 2,535: the
doc's flagship "96-98%, refunded seconds later" and its "with >=5 pts still
ahead, 415/415 (100%)" conditional are true by construction, not measured.

This script re-measures the same events looking only forward from the moment
the counter-move triggers:

  (a) resolution      P(a new move-direction extreme prints within HORIZON_MIN
                      minutes of the event) -- the re-entry trigger actually
                      firing, on a clock, with no knowledge of where the move
                      eventually tops out.
  (b) adverse         the worst excursion beyond the standing extreme between
                      the event and its resolution (or 10:30 if it never
                      resolves): median / p90 / max / P(>= 8 pts). This is
                      what the position endures to collect the resolution.
  (c) stop economics  for each stop distance S in STOPS: how often S fires,
                      and what stopping there costs against the endure
                      baseline, in ES points per day.

What is still hindsight, stated plainly: the primary move's *window and
direction* come from `morning_flush_study.json`, exactly as in the original
study -- this script does not solve direction and does not claim to. What has
been removed is the use of the move's terminal extreme to decide the OUTCOME
of an event. The measurement below is forward-looking within a
hindsight-selected window; it is not a tradeable backtest.

Stop-economics model (per event, ES points, signed so + is with the move):
  Both paths start in position at `ext`, the standing extreme when the
  counter-move begins -- the study's own re-entry model puts you there, long
  the breakout that printed it. An episode ends at RESOLUTION (first tick
  strictly beyond `ext` in the move direction) or at the 10:30 window close if
  resolution never comes.
    endure   hold through; episode P&L = (p_end - ext) * dir
    stop S   exit at the first tick at or beyond ext - S*dir; re-enter at the
             resolution tick if the episode resolves, paying FRICTION_PTS for
             that extra attempt. If it never resolves, the stop path sits flat
             into the close and pays no re-entry friction.
  Both paths hold the same position at the same price at the episode's end, so
  the difference is attributable to the stop alone and the per-event
  differences sum coherently across a day. Events where the worst adverse
  excursion never reaches S contribute exactly zero.

Section 4 is a control for the doc's dip-entry paragraph (audit §6.2): the
study only ever ran the dip lane nested inside `for cap in (2, 5)`, so the
liberal re-entry that is the lane's whole point was never simulated. This
re-runs the study's own `simulate()` with the attempt cap removed.

Usage:
    .venv/bin/python3 scripts/measurement/morning_flush_forward_stats.py
    .venv/bin/python3 scripts/measurement/morning_flush_forward_stats.py \
        --study data/measurement/morning_flush_oos.json \
        --out data/measurement/morning_flush_forward_stats_oos.json

Output: data/measurement/morning_flush_forward_stats.json + summary to stderr.
Re-runnable; the output file is regenerated whole each run.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from market.orderflow.replay import read_corpus_day  # noqa: E402
# Reused read-only: FRICTION_PTS and simulate() must not drift from the study
# that produced the numbers this script is correcting.
import morning_flush_study as mfs  # noqa: E402

CT = ZoneInfo("America/Chicago")
STUDY = ROOT / "data" / "measurement" / "morning_flush_study.json"
OUT = ROOT / "data" / "measurement" / "morning_flush_forward_stats.json"
W_START = time(8, 30)
W_END = time(10, 30)

EVENT_PTS = 2.0        # counter-move from the standing extreme that opens an event
HORIZON_MIN = 15       # minutes the new extreme gets to print, for (a)
STOPS = (2.0, 4.0, 8.0, 12.0)   # stop distances priced in (c), ES pts
ADVERSE_ALERT = 8.0    # the "structural stop" the anatomy doc used to assert (§6.6)
# Dip-lane control (§4). DIP_TURN is a module-level constant inside
# morning_flush_study, so varying it means rebinding the attribute; the study
# file itself is never modified. See `patched_dip_turn`.
DIP_LANE_TURNS = (1.5, 3.0)
DIP_LANE_TRIGGER = 5.0
DIP_LANE_STOP = 2.0
DIP_LANE_ENTRY = 2.0
DIP_LANE_CAPS = (None, 2, 5)


def pct(vals, q):
    """Percentile by nearest-rank on the sorted sample (no interpolation).

    Rank-based rather than interpolated because these are tick-quantised
    prices: an interpolated p90 of 12.375 names a price level that never
    printed. Nearest-rank returns an observed excursion.
    """
    if not vals:
        return None
    s = sorted(vals)
    k = min(len(s) - 1, max(0, round(q * (len(s) - 1) + 1e-9)))
    return s[k]


def median(vals):
    return statistics.median(vals) if vals else None


@contextmanager
def patched_dip_turn(turn: float):
    """Temporarily rebind morning_flush_study.DIP_TURN.

    `simulate()` reads DIP_TURN as a module global and takes no parameter for
    it, so a turn sweep has to rebind the attribute. Restored on exit so a
    later section cannot inherit a swept value.
    """
    prior = mfs.DIP_TURN
    mfs.DIP_TURN = turn
    try:
        yield
    finally:
        mfs.DIP_TURN = prior


def window_points(day: date):
    """[(ts, price)] for 08:30-10:30 CT, canonical corpus order.

    Raises FileNotFoundError if the day has no ES tape; the caller decides
    whether that is fatal.
    """
    trades = read_corpus_day(day)
    return [(t.ts, t.price) for t in trades if W_START <= t.ts.time() < W_END]


def move_start(points, stored, day: date):
    """The primary move's start tick, to full timestamp precision.

    The study JSON stores the start as "HH:MM:SS", and re-parsing that string
    lands up to a second EARLY -- enough extra ticks to shift the opening
    extreme and invent 5 spurious events at the 1-pt threshold. So the move is
    recomputed from the same tape with the study's own `primary_move()`, and
    the recomputation is cross-checked against the stored row: a mismatch in
    direction or size means the JSON and the corpus have diverged, and that is
    an error, not something to average over.
    """
    move = mfs.primary_move(points)
    if move is None:
        raise ValueError(f"{day}: primary_move() found no travel in the window")
    got_dir = "up" if move["dir"] == 1 else "dn"
    if got_dir != stored["dir"] or abs(move["size"] - stored["size"]) > 0.01:
        raise ValueError(
            f"{day}: recomputed primary move {got_dir} {move['size']} disagrees "
            f"with stored {stored['dir']} {stored['size']} — the study JSON and "
            f"the corpus are out of sync; re-run morning_flush_study.py")
    return move["start_ts"], (1 if move["dir"] == 1 else -1)


def counter_move_events(points, m_start: datetime, mdir: int, threshold: float):
    """Counter-moves >= `threshold` from the running extreme, forward only.

    Identical event generation to `morning_flush_study.resume_events` -- track
    the running extreme in the move's direction from the move's start to the
    WINDOW end, open an event the first tick the excursion reaches
    `threshold`, close it when a new extreme prints. That parity is deliberate:
    the point is to re-measure the SAME events, not a different event set.

    Each event carries only what was visible at its own trigger tick:
    dict(i0, t0, ext, trig_p). No terminal extreme, no `remaining`.
    """
    seg = [(ts, p) for ts, p in points if ts >= m_start]
    if not seg:
        return [], []
    ext_p = seg[0][1]
    pending = None
    events = []
    for i, (ts, p) in enumerate(seg):
        if (p - ext_p) * mdir > 0:
            if pending is not None:
                events.append(pending)
                pending = None
            ext_p = p
            continue
        if pending is None and (ext_p - p) * mdir >= threshold:
            pending = dict(i0=i, t0=ts, ext=ext_p, trig_p=p)
    if pending is not None:
        events.append(pending)
    return events, seg


def resolve_event(seg, ev, mdir, horizon: timedelta, stops):
    """Walk forward from an event to its resolution. No hindsight.

    Resolution is the first tick strictly beyond the standing extreme in the
    move's direction. Returns the 15-minute answer, the whole-window answer,
    the worst adverse excursion suffered on the way, and the fill price each
    stop in `stops` would have taken.
    """
    ext, i0 = ev["ext"], ev["i0"]
    deadline = ev["t0"] + horizon
    worst = 0.0            # to resolution / window end -- what enduring costs
    worst_h = 0.0          # to the HORIZON_MIN deadline -- comparable across events
    res_i = None
    stop_fill = {s: None for s in stops}
    for k in range(i0, len(seg)):
        ts, p = seg[k]
        if (p - ext) * mdir > 0:
            res_i = k
            break
        adverse = (ext - p) * mdir
        if adverse > worst:
            worst = adverse
        if ts <= deadline and adverse > worst_h:
            worst_h = adverse
        for s in stops:
            if stop_fill[s] is None and adverse >= s:
                stop_fill[s] = p
    resolved_ever = res_i is not None
    resolved_h = resolved_ever and seg[res_i][0] <= deadline
    end_p = seg[res_i][1] if resolved_ever else seg[-1][1]
    end_ts = seg[res_i][0] if resolved_ever else seg[-1][0]
    return dict(
        resolved_15=bool(resolved_h),
        resolved_ever=bool(resolved_ever),
        # truncated: the window closed before the 15-min clock ran out, so a
        # non-resolution here is censoring, not a failure to resume.
        truncated_15=bool(not resolved_h and seg[-1][0] < deadline),
        resolve_s=(round((end_ts - ev["t0"]).total_seconds(), 1)
                   if resolved_ever else None),
        adverse=round(worst, 2),
        adverse_15=round(worst_h, 2),
        end_p=end_p,
        end_gain=round((end_p - ev["ext"]) * mdir, 2),
        stop_fill=stop_fill,
    )


def stop_delta(ev, out, mdir, stop: float, friction: float):
    """P&L of stopping at `stop` minus P&L of enduring, for one event.

    Returns None when the stop never fires (the two paths are identical, and
    a zero would dilute the fired-event statistics).
    """
    fill = out["stop_fill"].get(stop)
    if fill is None:
        return None
    realized = (fill - ev["ext"]) * mdir        # negative: the loss taken
    if out["resolved_ever"]:
        # Re-enter at the resolution tick; both paths end long at that price.
        return round(realized - friction - out["end_gain"], 4)
    # Never resolved: the stop path sits flat into the close, endure eats the
    # whole unrecovered excursion. No re-entry, so no extra friction.
    return round(realized - out["end_gain"], 4)


def collect(study_rows, threshold, horizon, stops):
    """One record per counter-move event across every day in the study."""
    events = []
    day_points = {}
    skipped = []
    for row in study_rows:
        move = row.get("move")
        if not move:
            skipped.append((row.get("date"), "no primary move"))
            continue
        d = date.fromisoformat(row["date"])
        try:
            points = window_points(d)
        except Exception as e:                      # noqa: BLE001 - reported
            skipped.append((row["date"], f"corpus read failed: {e}"))
            continue
        if not points:
            skipped.append((row["date"], "no morning tape in window"))
            continue
        day_points[row["date"]] = points
        m_start, mdir = move_start(points, move, d)
        evs, seg = counter_move_events(points, m_start, mdir, threshold)
        if not seg:
            skipped.append((row["date"], "no tape after move start"))
            continue
        for ev in evs:
            out = resolve_event(seg, ev, mdir, horizon, stops)
            rec = dict(date=row["date"], dir=move["dir"],
                       t=ev["t0"].strftime("%H:%M:%S"),
                       ext=ev["ext"], trig_p=ev["trig_p"],
                       resolved_15=out["resolved_15"],
                       resolved_ever=out["resolved_ever"],
                       truncated_15=out["truncated_15"],
                       resolve_s=out["resolve_s"],
                       adverse=out["adverse"], adverse_15=out["adverse_15"],
                       end_gain=out["end_gain"])
            rec["stop_delta"] = {
                f"{s:g}": stop_delta(ev, out, mdir, s, mfs.FRICTION_PTS)
                for s in stops}
            events.append(rec)
    return events, day_points, skipped


def resolution_block(events):
    """(a) forward resolution rates.

    `n_truncated_15` is the censoring count: events whose 15-minute clock was
    still running when the 10:30 window closed. They are counted as
    non-resolutions in `p_new_extreme_15min` (that is the conservative
    reading), so the field is reported rather than silently absorbed.
    """
    n = len(events)
    res15 = sum(1 for e in events if e["resolved_15"])
    ever = sum(1 for e in events if e["resolved_ever"])
    trunc = sum(1 for e in events if e["truncated_15"])
    times = [e["resolve_s"] for e in events
             if e["resolved_15"] and e["resolve_s"] is not None]
    return dict(
        n_events=n,
        p_new_extreme_15min=round(res15 / n, 4) if n else None,
        n_new_extreme_15min=res15,
        p_new_extreme_ever=round(ever / n, 4) if n else None,
        n_never_resolved=n - ever,
        n_truncated_15=trunc,
        median_resolve_s=round(median(times), 1) if times else None,
        p90_resolve_s=pct(times, 0.90),
    )


def adverse_block(events, alert):
    """(b) what the position endures between the event and its resolution."""
    adv = [e["adverse"] for e in events]
    adv15 = [e["adverse_15"] for e in events]
    n = len(adv)
    return dict(
        n_events=n,
        median=median(adv), p90=pct(adv, 0.90), p95=pct(adv, 0.95),
        max=max(adv) if adv else None,
        p_ge_alert=round(sum(1 for x in adv if x >= alert) / n, 4) if n else None,
        alert_pts=alert,
        n_ge_alert=sum(1 for x in adv if x >= alert),
        horizon_capped=dict(median=median(adv15), p90=pct(adv15, 0.90),
                            max=max(adv15) if adv15 else None),
    )


def stop_block(events, n_days, stops):
    """(c) what each stop distance costs against the endure baseline."""
    out = {}
    for s in stops:
        key = f"{s:g}"
        fired = [e for e in events if e["stop_delta"][key] is not None]
        deltas = [e["stop_delta"][key] for e in fired]
        saves = [d for d in deltas if d > 0]
        costs = [d for d in deltas if d <= 0]   # break-even lands in `costs`
        per_day = {}
        for e in fired:
            per_day[e["date"]] = per_day.get(e["date"], 0.0) + e["stop_delta"][key]
        day_nets = [per_day.get(d, 0.0) for d in
                    {e["date"] for e in events}]
        out[key] = dict(
            stop_pts=s,
            n_fired=len(fired),
            fired_rate=round(len(fired) / len(events), 4) if events else None,
            stopouts_per_day=round(len(fired) / n_days, 2) if n_days else None,
            net_vs_endure_total=round(sum(deltas), 2),
            net_vs_endure_per_day_mean=(round(sum(deltas) / n_days, 2)
                                        if n_days else None),
            net_vs_endure_per_day_median=(round(median(day_nets), 2)
                                          if day_nets else None),
            worst_day=round(min(day_nets), 2) if day_nets else None,
            best_day=round(max(day_nets), 2) if day_nets else None,
            n_days_positive=sum(1 for x in day_nets if x > 0),
            n_days=len(day_nets),
            # the split that decides whether a stop is protection or a tax
            n_stops_that_saved=len(saves),
            pts_saved=round(sum(saves), 2),
            n_stops_that_cost=len(costs),
            pts_cost=round(sum(costs), 2),
            median_delta_when_fired=(round(median(deltas), 2) if deltas else None),
        )
    return out


def dip_lane_block(study_rows, day_points):
    """(4) the dip-entry lane with the study's attempt cap removed (audit §6.2).

    The anatomy doc calls this lane "unresolved" and the audit package calls
    it "artifact-prone"; neither states that uncapped -- the only form in which
    "liberal re-entry" is actually being tested -- it is catastrophic. This
    re-runs `morning_flush_study.simulate()` unchanged, varying only the
    attempt cap and the module's DIP_TURN.
    """
    rows = {}
    for turn in DIP_LANE_TURNS:
        with patched_dip_turn(turn):
            for cap in DIP_LANE_CAPS:
                nets, attempts = [], []
                for row in study_rows:
                    points = day_points.get(row["date"])
                    if not points:
                        continue
                    r = mfs.simulate(points, points[-1][1], DIP_LANE_TRIGGER,
                                     DIP_LANE_STOP, dip_entry=DIP_LANE_ENTRY,
                                     max_attempts=cap)
                    if r:
                        nets.append(r["chase_net"])
                        attempts.append(r["attempts"])
                if not nets:
                    continue
                rows[f"turn{turn:g}_cap{cap if cap else 'none'}"] = dict(
                    dip_turn=turn, cap=cap, n_days=len(nets),
                    median_net=round(median(nets), 2),
                    mean_net=round(sum(nets) / len(nets), 2),
                    worst_net=round(min(nets), 2),
                    days_positive=sum(1 for x in nets if x > 0),
                    median_attempts=median(attempts),
                    max_attempts_observed=max(attempts))
    return dict(trigger=DIP_LANE_TRIGGER, stop=DIP_LANE_STOP,
                dip_entry=DIP_LANE_ENTRY, cells=rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--study", type=Path, default=STUDY,
                    help="study JSON supplying move spans (default: %(default)s)")
    ap.add_argument("--out", type=Path, default=OUT,
                    help="output path (default: %(default)s)")
    ap.add_argument("--threshold", type=float, default=EVENT_PTS,
                    help="counter-move pts that open an event (default: %(default)s)")
    ap.add_argument("--horizon", type=int, default=HORIZON_MIN,
                    help="minutes the new extreme gets (default: %(default)s)")
    ap.add_argument("--no-dip-lane", action="store_true",
                    help="skip the §4 dip-lane control")
    args = ap.parse_args()
    args.study = args.study.resolve()
    args.out = args.out.resolve()

    if not args.study.exists():
        sys.exit(f"FATAL: study file not found: {args.study}\n"
                 f"Run morning_flush_study.py first.")
    try:
        study_rows = json.loads(args.study.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"FATAL: {args.study} is not valid JSON: {e}")
    if not study_rows:
        sys.exit(f"FATAL: {args.study} holds no days.")

    horizon = timedelta(minutes=args.horizon)
    try:
        events, day_points, skipped = collect(study_rows, args.threshold,
                                              horizon, STOPS)
    except ValueError as e:
        # move_start's integrity check: the study JSON disagrees with the tape.
        # Half a result would be worse than none — every number downstream is
        # anchored on the move span.
        sys.exit(f"FATAL: {e}")
    for d, why in skipped:
        print(f"{d} SKIP {why}", file=sys.stderr)
    if not events:
        sys.exit("FATAL: no counter-move events produced — refusing to write "
                 "an empty result. Check corpus coverage for the study days.")
    n_days = len({e["date"] for e in events})

    result = dict(
        bead="st-kmmg",
        generated=datetime.now(CT).isoformat(timespec="seconds"),
        study_source=(str(args.study.relative_to(ROOT))
                      if args.study.is_relative_to(ROOT) else str(args.study)),
        params=dict(event_threshold_pts=args.threshold,
                    horizon_min=args.horizon,
                    stops_pts=list(STOPS),
                    adverse_alert_pts=ADVERSE_ALERT,
                    friction_pts=mfs.FRICTION_PTS,
                    window=f"{W_START:%H:%M}-{W_END:%H:%M} CT"),
        n_days=n_days,
        resolution=resolution_block(events),
        adverse=adverse_block(events, ADVERSE_ALERT),
        stops=stop_block(events, n_days, STOPS),
        events=events,
    )
    if not args.no_dip_lane:
        result["dip_lane"] = dip_lane_block(study_rows, day_points)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))

    r, a = result["resolution"], result["adverse"]
    print(f"\n{r['n_events']} counter-move events >= {args.threshold:g} pts "
          f"over {n_days} days ({r['n_events'] / n_days:.1f}/day)",
          file=sys.stderr)
    print(f"  (a) new extreme within {args.horizon} min: "
          f"{r['n_new_extreme_15min']}/{r['n_events']} = "
          f"{100 * r['p_new_extreme_15min']:.1f}%   "
          f"(ever, by 10:30: {100 * r['p_new_extreme_ever']:.1f}%; "
          f"never: {r['n_never_resolved']})", file=sys.stderr)
    print(f"      median time to new extreme {r['median_resolve_s']}s, "
          f"p90 {r['p90_resolve_s']}s", file=sys.stderr)
    print(f"  (b) adverse before resolution: median {a['median']:.2f}  "
          f"p90 {a['p90']:.2f}  max {a['max']:.2f}  "
          f"P(>= {a['alert_pts']:g}) = {100 * a['p_ge_alert']:.1f}% "
          f"({a['n_ge_alert']} events)", file=sys.stderr)
    print("  (c) stop economics vs endure baseline "
          f"(friction {mfs.FRICTION_PTS:g} pt/re-entry):", file=sys.stderr)
    print("      stop  fired  /day   net pts/day  median day  saved / cost",
          file=sys.stderr)
    for key in (f"{s:g}" for s in STOPS):
        b = result["stops"][key]
        print(f"      {b['stop_pts']:4.0f}  {b['n_fired']:5d}  "
              f"{b['stopouts_per_day']:5.2f}  {b['net_vs_endure_per_day_mean']:11.2f}  "
              f"{b['net_vs_endure_per_day_median']:10.2f}  "
              f"{b['n_stops_that_saved']:3d} (+{b['pts_saved']:.0f}) / "
              f"{b['n_stops_that_cost']:3d} ({b['pts_cost']:.0f})",
              file=sys.stderr)
    if "dip_lane" in result:
        print("  (4) dip lane, study simulate() with the cap removed:",
              file=sys.stderr)
        for k, c in result["dip_lane"]["cells"].items():
            print(f"      {k:16s} median {c['median_net']:9.2f} pts/day  "
                  f"{c['days_positive']}/{c['n_days']} positive  "
                  f"median attempts {c['median_attempts']:.0f}", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
