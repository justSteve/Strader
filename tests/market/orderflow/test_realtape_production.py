"""Thirty minutes of real tape at PRODUCTION settings, asserted by behaviour.
[st-mx8z]

The parity snapshot and the goldens run on a synthetic or fixture-scale tape
with the sweep floor lowered, and pinned output by hash; imbalance stacks,
large lots and divergence were never exercised at the thresholds that reach
Steve's screen. This is 2026-09-30 08:55-09:25 CT, cut from the corpus with
every fill of every match event kept (st-exmw), and each assertion names the
thing it expects — a change that moves one of them fails here by name, not as
a hash nobody can read.

Regenerate only by cutting the same window again (the cut is in the bead) —
never by repinning what the code now says.
"""
from pathlib import Path

import pytest

from market.orderflow.bars import build_bars
from market.orderflow.imbalance import find_stacks
from market.orderflow.replay import read_corpus_day
from market.signals.orderflow import DeltaDivergence, SweepPrint

FIXTURE = Path(__file__).parent.parent / "fixtures" / "es_ticks_realtape_20260930.jsonl.gz"


@pytest.fixture(scope="module")
def tape():
    return read_corpus_day(FIXTURE)


@pytest.fixture(scope="module")
def run(tape):
    import market.orderflow.engine as eng
    e = eng.OrderflowEngine()
    return e, e.run(tape)


def test_the_tape_is_whole(tape):
    # every fill kept: 44,683 prints, 159,807 contracts
    assert (len(tape), sum(t.size for t in tape)) == (44683, 159807)


def test_the_one_order_that_crossed_three_priced_levels_is_the_sweep(run):
    _, sigs = run
    sweeps = [s for s in sigs if isinstance(s, SweepPrint)]
    assert [(s.timestamp.strftime("%H:%M:%S"), s.direction, s.total_size, s.level_sizes)
            for s in sweeps] == [
        ("09:20:10", "buy", 210, ((7775.25, 27), (7775.5, 99), (7775.75, 84)))]


def test_a_big_order_at_one_price_is_not_a_sweep(run):
    """09:01:21: 928 bought, 872 of it at 7772.00 — Steve's 08-21 complaint
    shape. Large, aggressive, and one price: not a sweep."""
    _, sigs = run
    assert not any(isinstance(s, SweepPrint) and s.timestamp.strftime("%H:%M") == "09:01"
                   for s in sigs)


def test_the_divergences_are_the_two_bearish_ones(run):
    _, sigs = run
    divs = [(s.timestamp.strftime("%H:%M:%S"), s.kind, s.price_extreme, s.prior_extreme)
            for s in sigs if isinstance(s, DeltaDivergence)]
    assert divs == [("09:13:16", "bearish", 7773.0, 7769.75),
                    ("09:22:13", "bearish", 7779.0, 7776.0)]


def test_large_lots_and_cvd(run):
    e, _ = run
    assert e.large_lot_count == 7
    assert (e.last_large_lot.size, e.last_large_lot.price) == (113, 7772.0)
    assert e.cvd == -929


def test_the_imbalance_stacks_are_the_two_buy_stacks(tape):
    bars = list(build_bars(tape, n=2000, include_partial=True))
    stacks = [(st.timestamp.strftime("%H:%M:%S"), st.direction, st.prices)
              for b in bars for st in find_stacks(b)]
    assert stacks == [("09:00:00", "buy", (7767.75, 7768.0, 7768.25)),
                      ("09:01:21", "buy", (7771.5, 7771.75, 7772.0))]
