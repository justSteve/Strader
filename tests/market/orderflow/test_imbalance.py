from datetime import datetime
from zoneinfo import ZoneInfo

from market.entities.footprint import FootprintBar, FootprintCell
from market.orderflow.imbalance import find_imbalances, find_stacks
from market.signals.orderflow_config import IMBALANCE_FLOOR, IMBALANCE_RATIO, STACK_MIN, TICK

CENTRAL = ZoneInfo("America/Chicago")
TS = datetime(2026, 7, 2, 9, 0, 0, tzinfo=CENTRAL)


def _bar(cells):
    cells = tuple(sorted(cells, key=lambda c: c.price))
    return FootprintBar(symbol="ES.c.0", start_ts=TS, end_ts=TS, open=cells[0].price,
                        high=cells[-1].price, low=cells[0].price, close=cells[-1].price,
                        volume=sum(c.total for c in cells), delta=0, none_vol=0, cells=cells)


F, R = IMBALANCE_FLOOR, IMBALANCE_RATIO
P = 7500.0


def test_buy_imbalance_is_diagonal():
    # ask@P dominates bid@(P-1 tick); bid@P itself is huge but irrelevant
    bar = _bar([FootprintCell(P - TICK, bid_vol=int(F // R), ask_vol=0),
                FootprintCell(P, bid_vol=10 * F, ask_vol=F)])
    imbs = find_imbalances(bar)
    assert (P, "buy") in [(p, d) for p, d, _ in imbs]


def test_ratio_boundary_exclusive_below():
    below = int(F / R) + 1
    bar = _bar([FootprintCell(P - TICK, bid_vol=below, ask_vol=0),
                FootprintCell(P, bid_vol=0, ask_vol=F)])  # F < R*below -> no
    assert find_imbalances(bar) == []


def test_floor_suppresses_small_dominance():
    bar = _bar([FootprintCell(P - TICK, bid_vol=1, ask_vol=0),
                FootprintCell(P, bid_vol=0, ask_vol=F - 1)])  # 99x ratio, under floor
    assert find_imbalances(bar) == []


def test_zero_opposite_counts_as_dominance():
    bar = _bar([FootprintCell(P, bid_vol=0, ask_vol=F)])  # no P-1 cell at all
    imbs = find_imbalances(bar)
    assert [(p, d) for p, d, _ in imbs] == [(P, "buy")]


def test_stack_requires_consecutive_ticks():
    # STACK_MIN buy imbalances but with a one-tick hole -> no stack
    cells = [FootprintCell(P + k * TICK, 0, F * 2) for k in range(STACK_MIN + 1) if k != 1]
    bar = _bar(cells)
    assert find_stacks(bar) == []


def test_stack_detected_and_bounded():
    cells = [FootprintCell(P + k * TICK, 0, F * 2) for k in range(STACK_MIN)]
    bar = _bar(cells)
    (stack,) = find_stacks(bar)
    assert stack.direction == "buy"
    assert stack.prices == tuple(P + k * TICK for k in range(STACK_MIN))
    assert len(stack.ratios) == STACK_MIN
    assert stack.timestamp == bar.end_ts


def test_opposite_directions_do_not_merge():
    # buys then sells, each STACK_MIN long, adjacent — two stacks, not one
    buys = [FootprintCell(P + k * TICK, 0, F * 2) for k in range(STACK_MIN)]
    sell_base = P + (STACK_MIN + 2) * TICK
    sells = [FootprintCell(sell_base + k * TICK, F * 2, 0) for k in range(STACK_MIN)]
    stacks = find_stacks(_bar(buys + sells))
    assert [s.direction for s in stacks] == ["buy", "sell"]


def test_stacks_never_span_bars():
    half = [FootprintCell(P + k * TICK, 0, F * 2) for k in range(STACK_MIN - 1)]
    b1, b2 = _bar(half), _bar(half)
    assert find_stacks(b1) == [] and find_stacks(b2) == []
