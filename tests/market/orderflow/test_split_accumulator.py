"""SplitAccumulator — the live aggressor-split profile behind the footprint's
volume-profile panel. [st-n0qm.4, Watcher V2 Phase 2]

The invariant the panel rests on: it is a SECOND VIEW OF THE SAME TAPE the
cells show, not a second pipeline. So for every price P, buys[P] + sells[P]
must equal the sum over closed bars of cells[P].bid + cells[P].ask (plus the
partial bar's remainder), and none must equal Σ nv — because build_bars keeps
N out of cells too. If this ever breaks, the profile and the footprint would
disagree about how much traded at a price, and Steve would be right to trust
neither.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from market.entities.trade import Trade
from market.orderflow.anchored_profile import (
    SplitAccumulator, build_split_profile, profile_payload,
)
from market.orderflow.bars import build_bars
from market.orderflow.replay import read_corpus_day
from market.signals.orderflow_config import TICK

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "es_ticks_golden_20260702.jsonl"


@pytest.fixture(scope="module")
def trades():
    if not FIXTURE.exists():
        pytest.skip("golden fixture missing")
    return read_corpus_day(FIXTURE)


def test_profile_equals_sum_of_cells_including_partial(trades):
    acc = SplitAccumulator(1)
    for t in trades:
        acc.add(t)
    cells_bid: dict[int, int] = {}
    cells_ask: dict[int, int] = {}
    nv = 0
    for bar in build_bars(iter(trades), n=500, include_partial=True):
        nv += bar.none_vol
        for c in bar.cells:
            k = int(c.price // TICK)
            cells_bid[k] = cells_bid.get(k, 0) + c.bid_vol
            cells_ask[k] = cells_ask.get(k, 0) + c.ask_vol
    keys = set(cells_bid) | set(cells_ask) | set(acc.buys) | set(acc.sells)
    assert keys, "fixture produced no prices"
    for k in keys:
        # cells: bid_vol = sell-aggressor ('A'), ask_vol = buy-aggressor ('B')
        assert acc.sells.get(k, 0) == cells_bid.get(k, 0), f"sell side differs at tick {k}"
        assert acc.buys.get(k, 0) == cells_ask.get(k, 0), f"buy side differs at tick {k}"
    assert sum(acc.nones.values()) == nv


def test_build_split_profile_default_is_separate_and_matches_accumulator(trades):
    """The batch builder delegates to the accumulator and, since the Aggressor
    None Policy decision (Phase 4), defaults to ``separate`` like the live
    panel — one policy across the estate. ``halve`` stays opt-in. With ES
    (N == 0 on the fixture) the two policies agree exactly."""
    acc = SplitAccumulator(1)
    for t in trades:
        acc.add(t)
    batch = build_split_profile(trades)
    assert batch == acc.snapshot(none_policy="separate")
    assert batch == build_split_profile(trades, none_policy="separate")
    if sum(acc.nones.values()) == 0:
        assert batch == acc.snapshot(none_policy="halve")


def test_default_policy_never_invents_an_aggressor():
    t0 = datetime(2026, 8, 14, 8, 30, tzinfo=timezone.utc)
    prof = build_split_profile([_t(t0, 7800.0, 10, "B"), _t(t0, 7800.0, 3, "N")])
    assert prof.buy_volumes == (10,) and prof.sell_volumes == (0,)   # the N print is not a seller
    assert build_split_profile([_t(t0, 7800.0, 10, "B"), _t(t0, 7800.0, 3, "N")],
                               none_policy="halve").sell_volumes == (2,)   # opt-in: 3 → 1 buy + 2 sell


def _t(ts, price, size, side):
    return Trade(ts=ts, symbol="ES", instrument_id=1, price=price, size=size, side=side)


def test_none_policy_separate_vs_halve():
    t0 = datetime(2026, 8, 14, 8, 30, tzinfo=timezone.utc)
    acc = SplitAccumulator(1)
    acc.add(_t(t0, 7800.0, 10, "B"))
    acc.add(_t(t0, 7800.0, 4, "A"))
    acc.add(_t(t0, 7800.0, 3, "N"))
    sep = acc.snapshot("separate")
    assert sep.buy_volumes == (10,) and sep.sell_volumes == (4,) and sep.total == 14
    hal = acc.snapshot("halve")
    assert hal.buy_volumes == (11,) and hal.sell_volumes == (6,) and hal.total == 17


def test_seeded_snapshot_and_holes_and_payload_shape():
    t0 = datetime(2026, 8, 14, 13, 30, tzinfo=timezone.utc)
    acc = SplitAccumulator(1)
    for i in range(10):
        acc.add(_t(t0 + timedelta(seconds=i), 7800.0 + (i % 3) * TICK, 5, "B" if i % 2 else "A"))
    acc.mark_seeded()
    assert acc.seeded["n"] == 10
    # a 12-hour gap = a hole; then today's prints
    t1 = t0 + timedelta(hours=12)
    for i in range(6):
        acc.add(_t(t1 + timedelta(seconds=i), 7801.0 + (i % 2) * TICK, 7, "B"))
    assert acc.holes and acc.holes[0][0] == t0 + timedelta(seconds=9) and acc.holes[0][1] == t1
    p = profile_payload(acc, anchor="prior-rth", anchor_ts=t0, session_day="2026-08-15")
    for k in ("v", "anchor", "anchor_ts", "session_day", "bucket", "n", "first_ts", "last_ts",
              "hole", "lo_tick", "buy", "sell", "none", "seeded", "va"):
        assert k in p, k
    assert p["n"] == 16 and len(p["buy"]) == len(p["sell"]) == len(p["none"])
    assert p["lo_tick"] == int(7800.0 // TICK)
    assert len(p["seeded"]["buy"]) == len(p["buy"]) and p["seeded"]["n"] == 10
    assert sum(p["buy"]) + sum(p["sell"]) == 10 * 5 + 6 * 7
    assert p["hole"] == [[(t0 + timedelta(seconds=9)).isoformat(), t1.isoformat()]]
    assert isinstance(p["va"]["poc"], float)


def test_empty_payload_is_honest():
    t0 = datetime(2026, 8, 14, 13, 30, tzinfo=timezone.utc)
    p = profile_payload(SplitAccumulator(1), anchor="prior-rth", anchor_ts=t0, session_day="2026-08-15")
    assert p["n"] == 0 and "buy" not in p and p["hole"] == []


def test_prior_trading_day():
    from strader.market_calendar import prior_trading_day
    assert prior_trading_day(date(2026, 8, 17)) == date(2026, 8, 14)   # Mon → Fri
    assert prior_trading_day(date(2026, 8, 16)) == date(2026, 8, 14)   # Sun → Fri
    assert prior_trading_day(date(2026, 8, 14)) == date(2026, 8, 13)
    assert prior_trading_day(date(2026, 9, 8)) == date(2026, 9, 4)     # Labor Day 09-07 skipped


def test_iter_trades_windows_the_day(trades):
    from market.orderflow.tradesource import iter_trades
    mid = trades[len(trades) // 2].ts
    tail = list(iter_trades(FIXTURE, start_ts=mid))
    assert tail and all(t.ts >= mid for t in tail)
    assert tail[-1] == trades[-1]
    head = list(iter_trades(FIXTURE, end_ts=mid))
    assert head and all(t.ts < mid for t in head)
    assert len(head) + len(tail) == len(trades)
