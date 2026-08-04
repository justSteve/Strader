#!/usr/bin/env python3
"""Render the live footprint page — the drill surface with an empty tape. [st-re1o]

Same template, same renderer, no bars baked in: the page opens empty and fills
from the bridge as `live_footprint_feed.py` pushes closed bars. That is the
point — one surface, so every rep Steve has banked against replay transfers to
the live session without a second set of habits.

The output path is a CONTRACT, like the desk pages: /tmp/desk-live-footprint.html.
Steve parks a browser tab there and refreshes it; it does not change per day,
because a live chart that moves address every morning is a bookmark that breaks
every morning.

Usage:
    # Stand up the page for today (open the tab, then start bridge + feeder)
    .venv/bin/python scripts/live_footprint_page.py

    # Full live stack, in three panes:
    #   1. .venv/bin/python scripts/drill_bridge.py
    #   2. .venv/bin/python scripts/corpus_stream_databento.py --streams es --now
    #   3. .venv/bin/python scripts/live_footprint_feed.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import central_date            # noqa: E402
from market.orderflow.anchors import mancini_levels_for  # noqa: E402
from market.signals.orderflow_config import TICK, VOLUME_BAR_N  # noqa: E402

logger = logging.getLogger("live_footprint_page")

TEMPLATE = Path(__file__).parent / "orderflow_drill_template.html"
MARKER = "/*__DRILL_DATA__*/null"
DEFAULT_OUT = Path("/tmp/desk-live-footprint.html")


def live_payload(day: _date, bar_n: int, mancini: list[float]) -> dict:
    """The empty-tape payload. Shape matches orderflow_drill.bars_payload.

    ``meta.source = "live"`` is the switch the template reads to enable the bar
    poller, suppress the guess-then-reveal quiz, and stop treating the end of
    the array as the end of the session.
    """
    return {
        "meta": {
            "symbol": "ES.c.0",
            "date": day.isoformat(),
            "bar_n": bar_n,
            "tick": TICK,
            "n_bars": 0,
            "contracts": 0,
            "source": "live",
            "candles_file": "",
        },
        "_candles": [],
        # Session-derived chips need bars to exist; live starts with none and
        # the Mancini levels carry the day until the session builds its own.
        "levels": {},
        "bars": [],
        "mancini_candidates": mancini,
        "anatomy": {"instances": []},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="session day YYYY-MM-DD (default: today CT)")
    ap.add_argument("--bar-n", type=int, default=VOLUME_BAR_N)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--mancini-levels",
                    help="comma-separated ES levels; default reads the day's parse")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date) if args.date else central_date()
    if args.mancini_levels:
        mancini = [float(x) for x in args.mancini_levels.split(",") if x.strip()]
    else:
        try:
            mancini = mancini_levels_for(day)
        except Exception as e:  # noqa: BLE001 — a missing parse must not block the chart
            logger.warning("no Mancini levels for %s (%s) — chart opens without them", day, e)
            mancini = []

    template = TEMPLATE.read_text(encoding="utf-8")
    if MARKER not in template:
        raise SystemExit(f"template {TEMPLATE} missing data marker")
    payload = live_payload(day, args.bar_n, mancini)
    out = Path(args.out)
    out.write_text(template.replace(MARKER, json.dumps(payload, separators=(",", ":"))),
                   encoding="utf-8")

    print(f"live footprint page: {out}")
    print(f"  day={day}  N={args.bar_n} contracts/bar  mancini levels={len(mancini)}")
    print("  waiting on: drill_bridge.py, then live_footprint_feed.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
