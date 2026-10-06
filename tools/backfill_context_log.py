#!/usr/bin/env python3
"""Backfill the live context log for a past day from what was logged. [st-2rsz]

    .venv/bin/python tools/backfill_context_log.py --day 2026-10-02
    .venv/bin/python tools/backfill_context_log.py --day 2026-10-06 --verify-bridge

The context log (``market/orderflow/context_log.py``) records Fuel and GEX as
the page saw them, starting with the feeder that carries it. Earlier days have
the feeder's run log and the corpus but no context log. This rebuilds it.

WHAT IS EXACT AND WHAT IS NOT. Measured on 2026-10-06 against the bridge, which
holds what the page actually received. Read before quoting a backfilled line.

  * Exact: the bars (the parity rebuild: same tape, same ``build_bars``, the
    last run's ``bar_n``), the Mancini set (the run header), and so Fuel's four
    tape components (underwater volume, lid rejections, absorbed dips, thinness).
    These are pure functions of the bar stream (fuel.py, Determinism).
    Measured: all 33 live Fuel lines that day, every tape component identical.
  * GEX, to within one bar a day: re-read from the corpus ``gexbot.jsonl`` with
    the same ``GexContext``. A poll is stamped with its pull START
    (``ts_pull_utc``); the nine-endpoint pull lands in the file seconds later, and
    live could only use it once it had landed. No write time is recorded, so the
    backfill assumes a fixed arrival lag. Measured mismatches over 327 bars by lag:
    0 s 33 · 4 s 23 · 8 s 7 · **10 s 1** · 12 s 4 · 20 s 23. 10 s it is. The
    residue is a pull that landed unusually fast or slow.
  * Not reproducible: Fuel's level HISTORY ("touched Nx / defended Nx"). It
    came from the level-state file, which the tracker rewrites all session, and
    touch counts are not stored with times, so the history at 09:38 cannot be
    recovered from the end-of-day file. Before st-2rsz the live line was frozen
    at its first load anyway. Backfilled Fuel therefore runs with no history
    and says "no level history". It never invents a count.
  * Days whose tape no longer rebuilds the live bars are REFUSED, not
    approximated. Measured 2026-10-06: every run-log day before 10-01 rebuilds
    3–7% more volume than its live bars held, with zero bar boundaries in
    common. The page drew different bars, so context would attach to bars
    Steve never saw. 10-01 through 10-06 align exactly.
  * The SPX→ES basis: its 1 Hz source was retired 2026-09-08, so live ``bs``
    was absent from then on and the backfill leaves it absent too.

Every row is written under a run header carrying ``"backfill": true`` and the
code revision, so a reader can tell a backfilled line from a live one. The tool
refuses to overwrite an existing context log unless ``--force`` is given. A live
log is the better record.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from datetime import date as _date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from market.corpus.paths import gexbot_path                       # noqa: E402
from market.orderflow.bars import build_bars                      # noqa: E402
from market.orderflow.context_log import context_log_path         # noqa: E402
from market.orderflow.fuel import FuelTracker                     # noqa: E402
from market.orderflow.gex_context import GexContext               # noqa: E402
from market.orderflow.replay import read_corpus_day               # noqa: E402
from market.orderflow.run_log import code_revision, read_runs, run_log_path  # noqa: E402

logger = logging.getLogger("backfill_context_log")
GEX_ARRIVAL_LAG_S = 10.0      # measured 2026-10-06 — see docstring
# Fuel reached the page in 5122fe8 (2026-08-24 05:52 CT, st-aq1n). A run that
# started before that never showed a Fuel line, and backfilling one would put a
# line on a card that the page never printed. GEX (445ebe0, 08-06) predates every
# run log.
FUEL_SINCE = datetime(2026, 8, 24, 5, 52)


class _AsOf:
    """A bar seen by GexContext as of ``lag`` seconds before its close: a poll
    pulled in that last window had not landed when the live feeder stamped it."""

    def __init__(self, bar, lag: float):
        self.end_ts = bar.end_ts - timedelta(seconds=lag)
        self.close, self.high, self.low = bar.close, bar.high, bar.low


def rebuild(day: _date) -> tuple[dict, list[dict]]:
    """(header, ctx rows) for ``day``'s last logged run. Exits on misalignment."""
    runs = read_runs(run_log_path(day))
    if not runs:
        sys.exit(f"no run log for {day} — nothing to align a backfill to")
    run = runs[-1]
    mancini = [float(p) for p in run.meta.get("mancini") or []]
    bars = list(build_bars(iter(read_corpus_day(day)), n=run.bar_n))
    # Alignment is the precondition for every row: a backfill whose bar i is not
    # the live bar i would attach context to the wrong bar on the card.
    n = min(len(bars), len(run.bars))
    bad = [i for i in range(n) if bars[i].end_ts.isoformat() != run.bars[i]["t1"]]
    if bad or n == 0:
        sys.exit(f"{day}: rebuilt bars do not align with the run log "
                 f"(first mismatch at bar {bad[0] if bad else 0}) — refusing to backfill")
    gp = gexbot_path(day)
    gex = GexContext(gp) if gp.exists() else None
    try:
        fuel_shown = datetime.fromisoformat(run.started).replace(tzinfo=None) >= FUEL_SINCE
    except ValueError:
        fuel_shown = day > FUEL_SINCE.date()
    # no history: see docstring
    fuel = FuelTracker(mancini) if (mancini and fuel_shown) else None
    rows = []
    for i, bar in enumerate(bars[:n]):
        g = None
        if gex is not None:
            gex.refresh()
            g = gex.for_bar(_AsOf(bar, GEX_ARRIVAL_LAG_S), basis=None)
            if g:   # age as live measured it: from the real close, not the shifted one
                g = g | {"age_s": round((bar.end_ts - datetime.fromisoformat(
                    g["ts"].replace("Z", "+00:00"))).total_seconds(), 1)}
        f = fuel.on_bar(bar) if fuel is not None else None
        if f is not None:
            f = f | {"bar_i": i}
        rec = {"k": "ctx", "i": i, "t1": bar.end_ts.isoformat()}
        if g:
            rec["gex"] = g
        if f:
            rec["fuel"] = f
        if len(rec) > 3:
            rows.append(rec)
    header = {"k": "run", "day": day.isoformat(), "started": run.started,
              "backfill": True, "backfilled_at": datetime.now().isoformat(timespec="seconds"),
              "bars": n, "fuel": fuel is not None,
              "fuel_why": ("as the page showed it" if fuel is not None else
                           "run predates Fuel (5122fe8)" if not fuel_shown else
                           "no Mancini set in this run — the page showed no Fuel either"),
              "code": code_revision(),
              "note": "rebuilt from run log + corpus; Fuel level history not reproducible"}
    return header, rows


def _tape_part(reason: str) -> str:
    """A Fuel reason minus its history phrase — the part a backfill must match."""
    return reason.split(" — ", 1)[0] + " — " + reason.split(" · ", 1)[1] if " · " in reason else reason


def verify_against_bridge(day: _date, rows: list[dict]) -> int:
    """Compare against what the page received today. Returns mismatch count."""
    with urllib.request.urlopen("http://127.0.0.1:7788/bars?since=0", timeout=10) as r:
        d = json.load(r)
    if (d.get("meta") or {}).get("day") != day.isoformat():
        sys.exit("the bridge is not serving that day — --verify-bridge only works for today")
    live = {i: b for i, b in enumerate(d["bars"])}
    mine = {r["i"]: r for r in rows}
    live_fuel = {i: e for i, b in live.items() for e in b.get("ev", []) if e.get("type") == "Fuel"}
    bad = 0
    for i in sorted(set(live_fuel) | {i for i, r in mine.items() if "fuel" in r}):
        lf, mf = live_fuel.get(i), (mine.get(i) or {}).get("fuel")
        if not lf or not mf or _tape_part(lf["reason"]) != _tape_part(mf["reason"]):
            bad += 1
            print(f"FUEL bar {i + 1}: live={lf and lf['reason']!r}\n            backfill={mf and mf['reason']!r}")
    gex_bad = sum(1 for i, b in live.items() if i in mine or b.get("gex")
                  if {k: v for k, v in (b.get("gex") or {}).items() if k not in ("age_s",)}
                  != {k: v for k, v in ((mine.get(i) or {}).get("gex") or {}).items() if k not in ("age_s",)})
    print(f"fuel: {len(live_fuel)} live, {sum('fuel' in r for r in rows)} backfilled, "
          f"{bad} differ in tape components · gex: {gex_bad} of {len(live)} bars differ")
    return bad + gex_bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--day", required=True)
    ap.add_argument("--force", action="store_true", help="overwrite an existing context log")
    ap.add_argument("--verify-bridge", action="store_true",
                    help="compare to the bridge (today only) and write nothing")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    day = _date.fromisoformat(a.day)
    header, rows = rebuild(day)
    if a.verify_bridge:
        return 1 if verify_against_bridge(day, rows) else 0
    out = context_log_path(day)
    if out.exists() and not a.force:
        sys.exit(f"{out} exists (a live log is the better record) — --force to replace")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, separators=(",", ":"), default=str) + "\n"
                           for r in [header, *rows]), encoding="utf-8")
    print(f"{out}: {header['bars']} bars aligned · {sum('fuel' in r for r in rows)} fuel · "
          f"{sum('gex' in r for r in rows)} gex rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
