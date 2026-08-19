#!/usr/bin/env python3
"""FootPrint replay drill launcher — one corpus day, as-if-live. [st-055]

One command per drill day:
  1. RECORD  — run the production classifier/recognizer stack over the day's
     tape and append the measured record (session_record.record_day).
  2. SURFACE — generate the footprint drill HTML via the same
     bars_payload/render path as scripts/orderflow_drill.py (identical
     surface, identical anchor rule) and open it in the Windows browser.
     Watch at speed 1x for as-if-live pacing.

The computation path holds zero wall-clock reads (st-055 plan), so the
record is byte-identical to what a live session over the same tape would
emit — recording fast and watching paced are the same measurement.

Usage:
    .venv/bin/python scripts/replay_day.py --date 2026-07-13
    .venv/bin/python scripts/replay_day.py --date 2026-07-13 --record-only
    .venv/bin/python scripts/replay_day.py --date 2026-07-13 --mancini-levels 6212,6230
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.anchors import levels_from_arg              # noqa: E402
from market.orderflow.session_record import record_day            # noqa: E402
from market.signals.orderflow_config import VOLUME_BAR_N          # noqa: E402
from scripts.orderflow_drill import bars_payload, open_in_browser, render  # noqa: E402

logger = logging.getLogger("replay_day")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Launch a FootPrint replay drill day [st-055]")
    ap.add_argument("--date", required=True, help="Corpus day YYYY-MM-DD")
    ap.add_argument("--bar-n", type=int, default=VOLUME_BAR_N,
                    help=f"Contracts per bar (default {VOLUME_BAR_N})")
    ap.add_argument("--mancini-levels", help="Comma-separated ES levels to anchor "
                    "BOTH the record and the drill (overrides the labeled-corpus "
                    "lookup); PRICE or PRICE:KIND, KIND = support|resistance|pivot, "
                    "bare = support (e.g. 6212,6230:resistance)")
    ap.add_argument("--record-only", action="store_true",
                    help="Write the measured record; skip the drill HTML")
    ap.add_argument("--no-open", action="store_true", help="Skip auto-opening the browser")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date)
    mancini, kinds = (levels_from_arg(args.mancini_levels)
                      if args.mancini_levels else (None, None))

    meta = record_day(day, bar_n=args.bar_n, mancini_prices=mancini, mancini_kinds=kinds)
    print(f"recorded: run {meta['run']} — {meta['n_events']} events "
          f"({meta['day_type']} day) -> {meta['path']}")
    if args.record_only:
        return 0

    out = Path(f"/tmp/desk-orderflow-drill-{day.isoformat()}.html")
    payload = bars_payload(day, args.bar_n, mancini_levels=mancini, mancini_kinds=kinds)
    render(payload, out)
    if not args.no_open:
        open_in_browser(out)
    print(f"drill ready: {out}  ({payload['meta']['n_bars']} bars, "
          f"{payload['meta']['contracts']:,} contracts) — set speed 1x for as-if-live")
    print(f"annotate:  .venv/bin/python scripts/replay_annotate.py --date {day.isoformat()} "
          f"--time HH:MM --text \"...\"")
    print(f"review:    .venv/bin/python scripts/replay_review.py --date {day.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
