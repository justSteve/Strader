"""The cell-cue page resolver's contract with the emission payload. [st-n0qm.2]

The live page (scripts/orderflow_drill_template.html, `resolveTargets`) names
the cells an emission is about from fields the emission ALREADY carries —
no engine change in Phase 1. That only holds while those fields keep their
names and their meaning; this test pins both, so an engine refactor that
renames `prices` or starts emitting a stack price that was never a traded cell
fails here rather than silently un-cueing the page.

What is pinned:
  * `parity.serialize()` emits, per type, the fields the resolver reads
    (ImbalanceStack.prices; SweepPrint.start_price/end_price;
    DeltaDivergence.price_extreme; SetupRecognition.anchor_price;
    AbsorptionRead.price) as finite numbers on the TICK grid.
  * Over the committed parity fixture, every ImbalanceStack.prices entry is a
    traded cell of the bar the stack was emitted under (bar_i), and every
    SweepPrint start/end lies inside its bar's range OR the previous bar's
    (the resolver's back-one rule) — the two claims the page's placement of
    exact cues rests on.

The JS side of the same contract is tools/cell_cue_check.mjs.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from market.orderflow.bars import build_bars
from market.orderflow.parity import (
    PARITY_ANCHORS, PARITY_BAR_N, PARITY_MANCINI, StackDriver, _overridden, serialize,
)
from market.orderflow.replay import read_corpus_day
from market.signals.orderflow_config import TICK

FIXTURE = Path(__file__).resolve().parents[1] / "market" / "fixtures" / "es_ticks_golden_20260702.jsonl"

# type -> the fields the page's resolver reads for that type
RESOLVER_FIELDS = {
    "ImbalanceStack": ("prices",),
    "SweepPrint": ("start_price", "end_price"),
    "DeltaDivergence": ("price_extreme",),
    "SetupRecognition": ("anchor_price",),
    "AbsorptionRead": ("price",),
}


def _on_grid(x: float) -> bool:
    return abs(round(x / TICK) * TICK - x) < 1e-6


@pytest.fixture(scope="module")
def drive():
    """Bars and per-bar events over the parity fixture, at fixture floors."""
    if not FIXTURE.exists():
        pytest.skip("parity fixture missing")
    trades = list(read_corpus_day(FIXTURE))
    bars, events = [], []
    with _overridden():
        driver = StackDriver(anchors=PARITY_ANCHORS, mancini_prices=PARITY_MANCINI)
        idx = 0
        for bar_i, bar in enumerate(build_bars(iter(trades), n=PARITY_BAR_N, include_partial=True)):
            vol, start = 0, idx
            while idx < len(trades) and vol < bar.volume:
                vol += trades[idx].size
                idx += 1
            bars.append(bar)
            events.append(driver.on_bar(bar_i, bar, trades[start:idx]))
        final = driver.finish(trades[idx:])
    return bars, events, final


def test_fixture_exercises_the_types_the_resolver_handles(drive):
    _, events, _ = drive
    seen = {e["type"] for evs in events for e in evs}
    # A contract test over a fixture that never emits the thing is vacuous.
    # The committed parity fixture emits setups and sweeps at fixture floors;
    # stacks are exercised separately below by driving the detector directly.
    assert "SweepPrint" in seen, seen
    assert "SetupRecognition" in seen, seen


def test_resolver_fields_are_present_finite_and_on_grid(drive):
    bars, events, final = drive
    checked = 0
    for evs in events + [final]:
        for e in evs:
            fields = RESOLVER_FIELDS.get(e["type"])
            if not fields:
                continue
            for f in fields:
                assert f in e, f"{e['type']} lost field {f!r}: {sorted(e)}"
                v = e[f]
                vals = v if isinstance(v, (list, tuple)) else [v]
                assert vals, f"{e['type']}.{f} is empty"
                for x in vals:
                    assert isinstance(x, (int, float)) and x == x, f"{e['type']}.{f} = {x!r}"
                    assert _on_grid(x), f"{e['type']}.{f} = {x} is off the {TICK} grid"
                    checked += 1
    assert checked > 0


def test_every_stack_price_is_a_traded_cell_of_its_bar(drive, monkeypatch):
    """Exact-cue guarantee: the page paints prices[] cells on bar_i and every
    one of them must exist there. The parity fixture emits no stack at
    production floors, so drive find_stacks at a permissive ratio/floor over
    the same bars — the invariant is structural (find_imbalances iterates
    bar.cells) and must hold at any threshold."""
    import market.orderflow.imbalance as imb
    monkeypatch.setattr(imb, "IMBALANCE_RATIO", 1.5)
    monkeypatch.setattr(imb, "IMBALANCE_FLOOR", 1)
    monkeypatch.setattr(imb, "STACK_MIN", 2)
    bars, _, _ = drive
    n_stacks = n_prices = 0
    for bar in bars:
        cell_prices = {round(c.price, 2) for c in bar.cells}
        for sig in imb.find_stacks(bar):
            e = serialize(sig)
            n_stacks += 1
            assert isinstance(e["prices"], list) and len(e["prices"]) >= 2
            for p in e["prices"]:
                assert round(p, 2) in cell_prices, \
                    f"stack price {p} is not a traded cell {sorted(cell_prices)}"
                assert _on_grid(p)
                n_prices += 1
    assert n_stacks > 0, "permissive thresholds produced no stack — test is vacuous"


def test_sweep_range_lies_in_its_bar_or_the_previous_one(drive):
    """The resolver files a sweep on bar_i unless its start is outside bar_i's
    range, in which case it looks back ONE bar. Pin that one bar is enough."""
    bars, events, _ = drive
    n = 0
    for bar_i, evs in enumerate(events):
        for e in evs:
            if e["type"] != "SweepPrint":
                continue
            lo, hi = sorted((e["start_price"], e["end_price"]))
            cands = [bars[bar_i]] + ([bars[bar_i - 1]] if bar_i else [])
            assert any(b.low - TICK / 2 <= lo and hi <= b.high + TICK / 2 for b in cands), \
                f"bar {bar_i}: sweep {lo}..{hi} outside bar and previous bar"
            n += 1
    assert n > 0


def test_serialize_keeps_prices_as_a_list_of_floats():
    """The page reads `e.prices` as an array; serialize() turns the tuple into a
    list. Pin the shape with a hand-built signal so a dataclass change shows."""
    from datetime import datetime, timezone
    from market.orderflow.imbalance import ImbalanceStack
    sig = ImbalanceStack(timestamp=datetime(2026, 8, 14, 13, 31, tzinfo=timezone.utc),
                         source="test", confidence=0.7, reason="r",
                         direction="buy", prices=(7800.0, 7800.25, 7800.5), ratios=(3.0, 3.1, 3.2))
    d = serialize(sig)
    assert d["type"] == "ImbalanceStack"
    assert isinstance(d["prices"], list) and d["prices"] == [7800.0, 7800.25, 7800.5]
