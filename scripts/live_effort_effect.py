#!/usr/bin/env python3
"""Live effort-vs-effect tape scorer — F1..F4, live-computable variant. [st-lxhz]

Steve, 2026-08-20 (st-cqwc): "the recognizer has to be scoring the F context,
doesn't it? ... The trader sitting in the chair using the emission as
guidance wants to know the F value as much as anything else." F1-F4 is
already built and ratified — market/orderflow/moves.py, corpus-measured in
docs/measurement/orderflow-fundamental-units.md (st-kaf) — but it grades
atoms by percentile rank against the FULL day (deliberately: "Hindsight is
deliberate," moves.py:18), which is only computable at session close. That
module's own doc says the live estimator is "unratified future work; nothing
in this document defines it" (§0.1). This script is that estimator's first
cut: real F1-F4 atoms (one_minute_atoms), graded causally against the day
SO FAR (moves.grade_atoms_developing — atom i never sees an atom after it,
pinned by test_developing_grade_is_causal_not_day_relative). The developing
grade is a DIFFERENT quantity from the hindsight one and lives in separately
named fields (effort_pct_dev, not effort_pct) so the two can never collide.

Cell names are the ratified ones (moves.CELL_NAMES), not invented ones:
    F1 conviction  — effort AND effect (the move is paid for)
    F2 absorption  — effort, no effect (someone is standing there)
    F3 hollow      — effect, no effort (price drifting on air)
    F4 dead        — neither

TWO KINDS OF LINE, never conflated:
  - A GRADED line prints once per completed clock-minute (the ratified atom
    boundary) — cell, dev-percentiles, cell_grade, and the atom's own raw
    OHLCV/delta printed alongside so a wrong grade and a wrong reading are
    distinguishable on sight (the whole point of watching this live). Every
    graded line says "(developing, n=N)" — cell_grade_dev is damped toward 0
    at low n (COO caught this: a single atom ranks itself at the 100th
    percentile by construction, which read as certainty, not the absence of
    it) — so the label carries the same caveat the field does.
  - A PARTIAL line prints only while price sits within CONFLUENCE_TOLERANCE_PTS
    of a Mancini level (market.signals.orderflow_config), on --partial-interval
    seconds, showing the in-progress minute's volume/move so far. It carries
    NO cell and NO percentile — an atom mid-minute is not a graded atom, and
    calling it one would be exactly the "different quantity, same name" error
    this design otherwise avoids.

Reuses the same tape pipeline the live footprint feeder uses (tail_rows /
ordered_trades — reconnect dedup + reorder buffer already hardened there), so
this is a second consumer of the same corpus tail, not a second Databento
connection.

Zero wall-clock reads: every decision here keys off Trade.ts, never
datetime.now(). --catch-up-only over a finished day is therefore the same
computation a live session over that tape would have produced, not an
approximation of it (same property scripts/replay_day.py documents for the
recognizer stack).

Usage:
    # Watch today's live tape (run this in a tmux pane)
    .venv/bin/python scripts/live_effort_effect.py

    # Sanity-check the grading against a day already on disk, no waiting
    .venv/bin/python scripts/live_effort_effect.py --date 2026-08-20 --catch-up-only
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root for market.*

from market.corpus.paths import central_date, resolve_existing  # noqa: E402
from market.orderflow.anchors import mancini_kinds_for, mancini_levels_for  # noqa: E402
from market.orderflow.moves import (CELL_NAMES, grade_atoms_developing,  # noqa: E402
                                    one_minute_atoms)
from market.orderflow.replay import es_day_path  # noqa: E402
from market.signals.orderflow_config import CONFLUENCE_TOLERANCE_PTS  # noqa: E402

# Sibling script, same directory — Python puts the invoked script's own dir
# (this one) on sys.path[0] automatically, so this resolves without a package.
from live_footprint_feed import ordered_trades, tail_rows  # noqa: E402

logger = logging.getLogger("effort_effect")


def nearest_level(price: float, levels: list[float], kinds: dict[float, tuple[str, ...]]):
    """(level, distance, kind) for the closest Mancini level, or None."""
    if not levels:
        return None
    lvl = min(levels, key=lambda p: abs(p - price))
    ks = kinds.get(lvl) if kinds else None
    return lvl, abs(lvl - price), (ks[0] if ks else "")


class LiveScorer:
    """Buckets trades into 1-minute atoms as they close, grades each closed
    atom causally, and offers an ungraded partial read of the in-progress
    minute. No wall-clock reads anywhere — every decision keys off Trade.ts."""

    def __init__(self, *, near_band: float, partial_interval: float,
                levels: list[float], kinds: dict[float, tuple[str, ...]]):
        self.near_band = near_band
        self.partial_interval = partial_interval
        self.levels = levels
        self.kinds = kinds

        self._minute_key = None
        self._minute_buf: list = []
        self._atoms: list = []
        self._last_partial_ts = None

    def _close_minute(self) -> str | None:
        atom = one_minute_atoms(self._minute_buf)[0]
        self._atoms.append(atom)
        self._minute_buf = []
        # cell_grade_dev is damped by n (COO, 2026-08-20 — a lone atom ranks
        # itself at the 100th percentile by construction, which is not
        # confidence), but the LABEL has to carry "developing" too, not just
        # the number — "F1 conviction" on screen imports the hindsight
        # meaning even when the field behind it is the causal one.
        dev = grade_atoms_developing(self._atoms)[-1]
        cell = dev["cell_dev"]
        return (f"{atom.ts:%H:%M} CT  {cell} (developing, n={dev['n_atoms']}) "
                f"{CELL_NAMES[cell]:<11} "
                f"ES o{atom.open:g} h{atom.high:g} l{atom.low:g} c{atom.close:g}  "
                f"vol {atom.volume} d{atom.delta:+d}  net {atom.net:+.2f} rng {atom.range_pts:.2f}"
                f"   dev: effort_pct {dev['effort_pct_dev']:.0f} effect_pct "
                f"{dev['effect_pct_dev']:.0f} grade {dev['cell_grade_dev']:.2f}")

    def _partial_line(self, t) -> str | None:
        if not self._minute_buf:
            return None
        near = nearest_level(t.price, self.levels, self.kinds)
        if near is None or near[1] > self.near_band:
            return None
        elapsed = (t.ts - self._minute_key).total_seconds()
        if (self._last_partial_ts is not None
                and (t.ts - self._last_partial_ts).total_seconds() < self.partial_interval):
            return None
        self._last_partial_ts = t.ts
        vol = sum(w.size for w in self._minute_buf)
        opn = self._minute_buf[0].price
        move = t.price - opn
        lvl, dist, kind = near
        return (f"{t.ts:%H:%M:%S} CT  partial ({elapsed:.0f}s in, ungraded)  "
                f"ES {t.price:g}  vol {vol} move {move:+.2f}  "
                f"near {lvl:g}{f' {kind}' if kind else ''} ({dist:+.2f})")

    def on_trade(self, t) -> list[str]:
        lines = []
        m = t.ts.replace(second=0, microsecond=0)
        if self._minute_key is not None and m != self._minute_key:
            line = self._close_minute()
            if line:
                lines.append(line)
        if self._minute_key is None or m != self._minute_key:
            self._minute_key = m
        self._minute_buf.append(t)

        p = self._partial_line(t)
        if p:
            lines.append(p)
        return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="corpus day YYYY-MM-DD (default: today CT)")
    ap.add_argument("--near-band", type=float, default=CONFLUENCE_TOLERANCE_PTS,
                    help=f"points from a Mancini level counted as 'near' for "
                         f"partial reads (default {CONFLUENCE_TOLERANCE_PTS}, "
                         f"the shared CONFLUENCE_TOLERANCE_PTS)")
    ap.add_argument("--partial-interval", type=float, default=10.0,
                    help="seconds between ungraded partial reads while near "
                         "a level (default 10)")
    ap.add_argument("--reorder-lag", type=float, default=2.0,
                    help="seconds of event-time buffer absorbing reconnect "
                         "disorder, same knob as the footprint feeder "
                         "(default 2.0)")
    ap.add_argument("--catch-up-only", action="store_true",
                    help="process what is already on disk and exit, instead "
                         "of following live — for sanity-checking the grading "
                         "against a day already on disk")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date) if args.date else central_date()
    path = es_day_path(day)
    resolved = resolve_existing(path)
    if resolved is None and args.catch_up_only:
        print(f"[FAIL] no ES corpus file for {day} at {path}", file=sys.stderr)
        return 1
    if resolved is not None:
        path = resolved

    try:
        levels = mancini_levels_for(day)
        kinds = mancini_kinds_for(day)
    except Exception as e:  # noqa: BLE001 — no anchors must not stop the tool
        logger.warning("no Mancini levels for %s (%s) — partial reads disabled", day, e)
        levels, kinds = [], {}

    print(f"# effort/effect scorer (live F1-F4) — {day}  "
         f"near<= {args.near_band}pt @ {args.partial_interval}s partial  "
         f"{len(levels)} levels loaded")

    scorer = LiveScorer(
        near_band=args.near_band,
        partial_interval=args.partial_interval, levels=levels, kinds=kinds,
    )

    rows = tail_rows(path, follow=not args.catch_up_only, pinned_day=day)
    for t in ordered_trades(rows, reorder_lag_s=args.reorder_lag):
        for line in scorer.on_trade(t):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
