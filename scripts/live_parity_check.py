#!/usr/bin/env python3
"""Did the live session emit what a replay of its tape recomputes? [st-x2mp]

Spec §5 says live == replay. The live feeder and the replay path drive the
SAME ``StackDriver`` through the SAME ``live_drive`` loop, so that is true by
construction — but "by construction" is an argument, not a measurement, and
this is the measurement. It closes acceptance criterion #4 on st-d5f (Phase B):
*a captured live hour replays to identical signals*.

WHAT IT COMPARES
    The live run log (``data/derived/live-parity/<day>.jsonl``, written by the
    feeder) against a fresh drive of the day's corpus tape through the same
    pipeline, with the same bar size, the same Mancini anchor set, and the same
    LiveAnchors rule the live run used. Bars first, then emissions.

WHY BARS FIRST
    A shifted bar boundary makes every later emission "differ" for one reason,
    and a report that lists four hundred emission mismatches when one late row
    moved a boundary is a report nobody reads. So the bar sequence is diffed
    first and the run stops at the first boundary that moves. Emission drift is
    only meaningful once boundaries agree.

WHAT A FAILURE MEANS
    Not "the engine is wrong" — both sides ran the same engine. It means the
    two sides did not see the same TRADES in the same ORDER. The live path
    holds rows for --reorder-lag seconds and releases them in order; the replay
    sorts the whole file by (ts, sequence). A reconnect redelivering rows
    staler than the lag is the known way for those to part company, and the
    first divergent bar's timestamp is where to look in the capture log.

WHAT IT DOES NOT CHECK
    The DRILL's emissions. The drill builds anchors with ``day_anchors``, which
    uses the session high/low — lookahead a live session cannot have. That
    divergence is designed and permanent (see anchors.LiveAnchors), so it is
    excluded here on purpose; folding it in would guarantee a red result that
    means nothing.

USAGE
    .venv/bin/python scripts/live_parity_check.py --date 2026-08-07
    .venv/bin/python scripts/live_parity_check.py --date 2026-08-07 --run 0
    .venv/bin/python scripts/live_parity_check.py            # most recent day

EXIT
    0 = the replay reproduced the run.  1 = divergence (detailed).
    2 = could not check (no log, no tape, no complete run).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import most_recent_session_day           # noqa: E402
from market.orderflow.anchors import LiveAnchors                  # noqa: E402
from market.orderflow.bars import build_bars                      # noqa: E402
from market.orderflow.parity import StackDriver, live_drive       # noqa: E402
from market.orderflow.replay import has_es_day, read_corpus_day   # noqa: E402
from market.orderflow.run_log import Run, bar_record, read_runs, run_log_path  # noqa: E402

logger = logging.getLogger("live_parity_check")

# Bar fields compared, in report order. Floats are compared exactly on purpose:
# both sides derive them from the same trade prices with no arithmetic, so an
# epsilon here would only hide a real disagreement about which trades landed.
BAR_FIELDS = ("t0", "t1", "o", "h", "l", "c", "v", "d", "nv")

# Emission fields that are pipeline OUTPUT. `timestamp` is included: a signal
# that fires on a different print is a different signal even when its numbers
# match.
_EV_SKIP = ("k",)


def replay_events(day: _date, *, bar_n: int, mancini: list[float]) -> tuple[list[dict], list[dict]]:
    """Drive the day's tape exactly as the live feeder drove it.

    Closed bars only and LiveAnchors, because those are the live rules — see
    the module docstring. Returns ``(bar_records, emissions)`` in the same
    shape the run log holds them.
    """
    trades = read_corpus_day(day)
    live_anchors = LiveAnchors(mancini)
    driver = StackDriver(anchors=live_anchors.anchors, mancini_prices=mancini)
    pending = list(trades)
    cursor = {"i": 0}

    def _closed_bars():
        # Bars close on known trade boundaries, so walk the trade list until
        # each bar's volume is covered — the same straddle convention the
        # feeder's take_bar_trades() reclaims a slice by.
        for bar in build_bars(iter(trades), n=bar_n):
            vol = 0
            start = cursor["i"]
            while cursor["i"] < len(pending) and vol < bar.volume:
                vol += pending[cursor["i"]].size
                cursor["i"] += 1
            yield bar, pending[start:cursor["i"]]

    bars: list[dict] = []
    events: list[dict] = []
    for bar_i, bar, _trades, evs in live_drive(_closed_bars(), driver, live_anchors):
        bars.append(bar_record(bar_i, bar))
        events.extend({"k": "ev"} | e for e in evs)
    events.extend({"k": "ev"} | e for e in driver.finish(pending[cursor["i"]:]))
    return bars, events


def diff_bars(live: list[dict], repl: list[dict]) -> list[str]:
    """First divergent bar only — see the module docstring on why."""
    out: list[str] = []
    if len(live) != len(repl):
        out.append(f"bar COUNT differs: live {len(live)}, replay {len(repl)}")
    for i, (a, b) in enumerate(zip(live, repl)):
        bad = [f for f in BAR_FIELDS if a.get(f) != b.get(f)]
        if bad:
            out.append(f"first divergent bar: index {i} (live t0={a.get('t0')})")
            for f in bad:
                out.append(f"    {f:>3}: live {a.get(f)!r}  replay {b.get(f)!r}")
            out.append("    a moved boundary here explains every later difference — "
                       "check the capture log around this timestamp for a reconnect")
            return out
    return out


def _ev_key(e: dict) -> tuple:
    return (e.get("bar_i"), e.get("type"), e.get("timestamp"))


def diff_events(live: list[dict], repl: list[dict]) -> list[str]:
    """Positional diff, reporting the first few disagreements with context."""
    out: list[str] = []
    if len(live) != len(repl):
        out.append(f"emission COUNT differs: live {len(live)}, replay {len(repl)}")
    shown = 0
    for i, (a, b) in enumerate(zip(live, repl)):
        if _ev_key(a) != _ev_key(b):
            out.append(f"emission {i}: live {_ev_key(a)}  replay {_ev_key(b)}")
            shown += 1
        else:
            fields = (set(a) | set(b)) - set(_EV_SKIP)
            bad = [f for f in sorted(fields) if a.get(f) != b.get(f)]
            if bad:
                out.append(f"emission {i} ({a.get('type')} bar {a.get('bar_i')}):")
                for f in bad:
                    out.append(f"    {f}: live {a.get(f)!r}  replay {b.get(f)!r}")
                shown += 1
        if shown >= 5:
            out.append("    ... stopping after 5; fix these and re-run")
            break
    # A count mismatch with no positional disagreement means one side simply
    # ran longer — name the tail rather than reporting "all clean, but".
    if len(live) != len(repl) and not shown:
        longer, label = (live, "live") if len(live) > len(repl) else (repl, "replay")
        extra = longer[min(len(live), len(repl)):]
        out.append(f"    {label} emitted {len(extra)} more: "
                   + ", ".join(f"{e.get('type')}@bar{e.get('bar_i')}" for e in extra[:5]))
    return out


def pick_run(runs: list[Run], which: int | None) -> Run | None:
    if not runs:
        return None
    if which is not None:
        return runs[which] if -len(runs) <= which < len(runs) else None
    # Default to the last COMPLETE run: an incomplete one was killed mid-session
    # and its tail is missing by definition, so diffing it reports a difference
    # that is about the kill, not about parity.
    for r in reversed(runs):
        if r.complete:
            return r
    return runs[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="corpus day YYYY-MM-DD (default: most recent session)")
    ap.add_argument("--run", type=int, default=None,
                    help="which run in the day's log (default: last complete; "
                         "negative indexes from the end)")
    ap.add_argument("--log", help="explicit run-log path (default: the day's)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date) if args.date else most_recent_session_day()
    path = Path(args.log) if args.log else run_log_path(day)
    if not path.exists():
        print(f"[SKIP] no live run log for {day} at {path}\n"
              f"       the feeder writes one unless --no-run-log; a session run "
              f"without it cannot be checked afterwards", file=sys.stderr)
        return 2
    if not has_es_day(day):
        print(f"[SKIP] no ES corpus tape for {day} — nothing to replay", file=sys.stderr)
        return 2

    runs = read_runs(path)
    run = pick_run(runs, args.run)
    if run is None:
        print(f"[SKIP] {path} holds no usable run", file=sys.stderr)
        return 2
    if not run.bar_n:
        print(f"[SKIP] run header carries no bar_n — written by an older feeder?",
              file=sys.stderr)
        return 2

    mode = "catch-up" if run.meta.get("catch_up") else "live"
    print(f"day {day} · run {run.started} ({mode}) · "
          f"{'complete' if run.complete else 'INCOMPLETE — died mid-session'}")
    print(f"  live:   {len(run.bars)} bars, {len(run.events)} emissions "
          f"(N={run.bar_n}, {len(run.mancini)} mancini anchors)")

    bars, events = replay_events(day, bar_n=run.bar_n, mancini=run.mancini)
    print(f"  replay: {len(bars)} bars, {len(events)} emissions")

    problems = diff_bars(run.bars, bars)
    if problems:
        print("\n[FAIL] bar sequence diverged:")
        for line in problems:
            print("  " + line)
        return 1

    problems = diff_events(run.events, events)
    if problems:
        print("\n[FAIL] bars agree, emissions diverged:")
        for line in problems:
            print("  " + line)
        return 1

    if not run.complete:
        print("\n[PASS-partial] everything the run recorded replays identically, "
              "but the run died before its end marker — the tail is unverified.")
        return 0
    print("\n[PASS] the replay reproduced the live run exactly — "
          f"{len(bars)} bars, {len(events)} emissions, field for field.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
