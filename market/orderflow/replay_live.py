"""Drive a day's tape exactly as the live feeder drove it. [st-x2mp, co-7kgte]

Closed bars only and ``LiveAnchors``, because those are the live rules (see
``market/orderflow/run_log.py``). Lived in ``scripts/live_parity_check.py``
until the day post-mortem needed the same drive for its backfill; a script is
not an importable home, so the function moved here and the checker imports it.
"""
from __future__ import annotations

from datetime import date as _date

from market.orderflow.anchors import Kinds, LiveAnchors
from market.orderflow.bars import build_bars
from market.orderflow.parity import StackDriver, live_drive
from market.orderflow.replay import read_corpus_day
from market.orderflow.run_log import bar_record


def replay_events(day: _date, *, bar_n: int, mancini: list[float],
                  kinds: Kinds | None = None) -> tuple[list[dict], list[dict]]:
    """Returns ``(bar_records, emissions)`` in the shape the run log holds them.
    ``kinds`` is the Mancini levels' anchor-kind map the live run used (its
    run-log header carries it); None replays every level as a support, which
    is what runs before 2026-08-19 watched."""
    trades = read_corpus_day(day)
    live_anchors = LiveAnchors(mancini, kinds=kinds)
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
