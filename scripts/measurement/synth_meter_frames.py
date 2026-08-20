#!/usr/bin/env python3
"""Synthetic continuation-meter frames from the ES corpus, and a flush-watcher
replay over them. [st-88ei]

WHY. Closing st-kos7 established that the flush watcher replays clean against
2026-08-04 and 08-05: zero would-alerts, both up days, and the trigger is
down-only. That proves it does not cry wolf on days it should ignore and
NOTHING about whether it catches a genuine flush. The known flush tapes are
2026-07-22 and 2026-07-31, and the live continuation-meter journal only begins
2026-08-03 — so no meter frames exist for either day, and none ever will.

A detector validated only on days it should ignore is not validated.

WHAT THIS DOES. Rebuilds meter-shaped frames from the ES tape we do have, then
runs the real `flush_watcher.evaluate` over them with a real `WatchState`. The
watcher code is imported, never reimplemented: a replay against a paraphrase of
the decision logic measures the paraphrase.

SCHEMA IDENTITY IS THE WHOLE BALL GAME. The acceptance criteria call schema
drift here "silently invalidates every replay", so:

  - `move` is built by `continuation_meter.primary_move` — the LIVE meter's own
    function, imported from the live module. The bead's text names
    `morning_flush_study.primary_move`, but that one returns `start_ts`/`end_ts`
    where the journal carries `start_t`/`end_t`, and it has no `contested` flag,
    which `flush_watcher.evaluate` reads. The meter's function is the
    schema-true one; using the study's would have produced frames the watcher
    silently mis-parses. Deviation from the bead is deliberate and recorded.
  - Frames are accumulated CAUSALLY: the move at minute i is computed over
    closes up to and including i, never the whole day. A non-causal frame makes
    every lead-time measurement meaningless.
  - Two keys are ADDED, never renamed: `synthetic: true` and
    `price_source: "ES"`. Extra keys are additive (the watcher reads by `.get`);
    a renamed one would be drift. They exist so no downstream reader can mistake
    these for live frames.

PRICE SOURCE. The live meter measures SPX from Schwab minute candles; this
measures ES from the Databento corpus. The 25-point trigger is applied to ES
points. ES and SPX travel near 1:1 in points, but they are not the same series
and the basis moves — every number out of this script is an ES-point number and
is labelled as such.

    .venv/bin/python scripts/measurement/synth_meter_frames.py --report
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from datetime import datetime, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "desk"))

from market.orderflow.moves import one_minute_atoms  # noqa: E402
from market.orderflow.replay import has_es_day, read_corpus_day  # noqa: E402

import continuation_meter as meter  # noqa: E402
import flush_watcher as watcher  # noqa: E402

FLUSH_DAYS = [_date(2026, 7, 22), _date(2026, 7, 31)]
OUT_JSON = ROOT / "data" / "measurement" / "flush_watcher_replay.json"


def synth_frames(day: _date) -> list[dict]:
    """Meter-shaped frames for one corpus day, one per RTH minute.

    Causal by construction: `closes` only ever holds minutes at or before the
    frame's own minute, so `primary_move` cannot see the future.
    """
    atoms = one_minute_atoms(read_corpus_day(day))
    closes: dict[datetime, float] = {}
    frames: list[dict] = []
    for a in atoms:
        if a.ts.time() < meter_open():
            continue
        closes[a.ts] = a.close
        mv = meter.primary_move(closes)
        if mv is not None:
            mv = dict(mv, start_t=mv["start_t"].isoformat(),
                      end_t=mv["end_t"].isoformat())
        frames.append({
            "ts": a.ts.isoformat(),
            "errors": [],
            "last_candle": a.ts.strftime("%H:%M"),
            "stale_min": 0.0,
            "traces_raw": {"tick": None, "add10": None, "vix5": None,
                           "vvix5": None, "spx5": None},
            "traces": {"tick": None, "add": None, "vix": None},
            "score": None,
            "score_mode": None,
            "levels": {"spx": a.close, "vix": None, "vvix": None, "term": None},
            "move": mv,
            "synthetic": True,
            "price_source": "ES",
        })
    return frames


def meter_open() -> time:
    """RTH open. The live meter fetches with need_extended_hours_data=False, so
    its `closes` start at the cash open; synthetic frames must start there too
    or the primary move is measured over a window the live one never sees."""
    return time(8, 30)


def replay(day: _date) -> dict:
    """Run the real watcher over one day of synthetic frames."""
    frames = synth_frames(day)
    state = watcher.WatchState()
    state.roll_day(day.isoformat())
    fires: list[dict] = []
    for f in frames:
        fire, reason = watcher.evaluate(f, state)
        if not fire:
            continue
        mv = f["move"]
        state.alerted_moves.add(watcher.move_key(mv))
        state.sent_today += 1
        started = datetime.fromisoformat(mv["start_t"])
        at = datetime.fromisoformat(f["ts"])
        fires.append({
            "fired_at": at.strftime("%H:%M"),
            "move_started": started.strftime("%H:%M"),
            # LAG, not lead: the watcher fires N minutes AFTER the move began. It
            # is not early warning and must never be quoted as such.
            "lag_min": round((at - started).total_seconds() / 60.0),
            "size_at_fire": mv["size"],
            "reason": reason,
        })
    graded = [f for f in frames if f["move"]]

    def _max_down(fs) -> float:
        worst = min((f["move"]["size"] * f["move"]["dir"] for f in fs),
                    default=0.0)
        return round(abs(worst), 2) if worst < 0 else 0.0

    # Two numbers, deliberately. The watcher only fires inside 08:30-11:00, so
    # the session figure explains days with a large down move that correctly
    # never fired (it arrived after the window) — reporting only the session
    # number would read as the trigger missing them. [st-88ei]
    in_window = [f for f in graded
                 if watcher.WINDOW_OPEN
                 <= datetime.fromisoformat(f["ts"]).timetz().replace(tzinfo=None)
                 <= watcher.WINDOW_CLOSE]
    return {
        "day": day.isoformat(),
        "frames": len(frames),
        "fires": fires,
        "fired": bool(fires),
        "max_down_move_pts": _max_down(graded),
        "max_down_in_window_pts": _max_down(in_window),
    }


def july_days() -> list[_date]:
    return [d for d in (_date(2026, 7, n) for n in range(1, 32))
            if has_es_day(d)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", nargs="*", help="ISO days; default = all July")
    ap.add_argument("--report", action="store_true",
                    help="write data/measurement/flush_watcher_replay.json")
    args = ap.parse_args()

    days = ([_date.fromisoformat(d) for d in args.days] if args.days
            else july_days())
    results = []
    for d in days:
        try:
            results.append(replay(d))
        except FileNotFoundError:
            print(f"{d}  NO ES CORPUS", file=sys.stderr)

    flush = [r for r in results if _date.fromisoformat(r["day"]) in FLUSH_DAYS]
    other = [r for r in results if _date.fromisoformat(r["day"]) not in FLUSH_DAYS]

    print(f"{'DAY':<12} {'FRAMES':>7} {'DOWN/win':>9} {'DOWN/day':>9} "
          f"{'FIRED':>6}  DETAIL")
    print("-" * 84)
    for r in results:
        tag = "FLUSH" if _date.fromisoformat(r["day"]) in FLUSH_DAYS else ""
        det = "; ".join(f"{f['fired_at']} at {f['size_at_fire']:.0f}pt "
                        f"(+{f['lag_min']}min)" for f in r["fires"]) or "-"
        print(f"{r['day']:<12} {r['frames']:>7} "
              f"{r['max_down_in_window_pts']:>9.2f} "
              f"{r['max_down_move_pts']:>9.2f} "
              f"{'YES' if r['fired'] else 'no':>6}  {det} {tag}")

    caught = sum(1 for r in flush if r["fired"])
    fp = sum(1 for r in other if r["fired"])
    print()
    print(f"flush days caught : {caught}/{len(flush)}")
    print(f"false positives   : {fp}/{len(other)} non-flush days fired")
    if flush:
        lags = [f["lag_min"] for r in flush for f in r["fires"]]
        if lags:
            print(f"lag behind move   : {min(lags)}-{max(lags)} min after it began")

    if args.report:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps({
            "generated_from": "ES corpus via synth_meter_frames.py [st-88ei]",
            "price_source": "ES",
            "trigger": {"flush_pts": watcher.FLUSH_PTS,
                        "flush_dir": watcher.FLUSH_DIR,
                        "window": [str(watcher.WINDOW_OPEN),
                                   str(watcher.WINDOW_CLOSE)],
                        "provisional": "every constant awaits st-rtuu"},
            "flush_days_caught": f"{caught}/{len(flush)}",
            "false_positive_days": f"{fp}/{len(other)}",
            "days": results,
        }, indent=2) + "\n")
        print(f"\nwrote {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
