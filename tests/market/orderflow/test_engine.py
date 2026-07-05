import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market.entities.trade import Trade
from market.orderflow.engine import OrderflowEngine
from market.signals.orderflow import DeltaDivergence, SweepPrint
from market.signals.orderflow_config import (
    LARGE_LOT_MEDIAN_WINDOW, PIVOT_FILTER_TICKS, SWEEP_MIN_SIZE, SWEEP_MIN_TICKS, TICK,
)

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 7, 2, 8, 30, 0, tzinfo=CENTRAL)


def _t(ms, price=7500.0, size=10, side="B"):
    return Trade(ts=T0 + timedelta(milliseconds=ms), symbol="ES.c.0", instrument_id=1,
                 price=price, size=size, side=side, sequence=ms)


# ── CVD ─────────────────────────────────────────────────────────────────────
def test_cvd_sum_and_none_bucket():
    e = OrderflowEngine()
    e.run([_t(0, size=60, side="B"), _t(1, size=25, side="A"), _t(2, size=40, side="N")])
    assert e.cvd == 35
    assert e.none_vol == 40


def test_cvd_resets_at_next_session_open():
    e = OrderflowEngine()
    e.process(_t(0, size=100, side="B"))
    assert e.cvd == 100
    nxt = Trade(ts=T0 + timedelta(days=1), symbol="ES.c.0", instrument_id=1,
                price=7500.0, size=5, side="A", sequence=1)
    e.process(nxt)
    assert e.cvd == -5  # fresh epoch, not 95


def test_out_of_order_raises():
    e = OrderflowEngine()
    e.process(_t(1000))
    with pytest.raises(ValueError, match="out-of-order"):
        e.process(_t(0))


# ── large-lot ───────────────────────────────────────────────────────────────
def test_large_lot_silent_during_warmup_then_fires():
    e = OrderflowEngine()
    e.process(_t(0, size=10_000))          # giant print during warm-up: silent
    assert e.large_lot_count == 0
    for i in range(1, LARGE_LOT_MEDIAN_WINDOW + 1):
        e.process(_t(i, size=2))
    e.process(_t(9_000_000, size=200))     # 200 >= 10 x median(2)
    assert e.large_lot_count == 1
    assert e.last_large_lot.size == 200


# ── sweeps ──────────────────────────────────────────────────────────────────
def test_buy_sweep_emitted_on_run_end():
    e = OrderflowEngine()
    sigs = []
    for k in range(SWEEP_MIN_TICKS):
        sigs += e.process(_t(k * 10, price=7500.0 + k * TICK, size=40, side="B"))
    sigs += e.process(_t(5000, price=7500.0, size=1, side="A"))  # gap+side ends run
    sweeps = [s for s in sigs if isinstance(s, SweepPrint)]
    assert len(sweeps) == 1
    s = sweeps[0]
    assert s.direction == "buy" and s.ticks_swept == SWEEP_MIN_TICKS and s.total_size == 120


def test_slow_walk_is_not_a_sweep():
    e = OrderflowEngine()
    sigs = []
    for k in range(SWEEP_MIN_TICKS):
        sigs += e.process(_t(k * 1000, price=7500.0 + k * TICK, side="B"))  # 1s gaps
    sigs += e.flush()
    assert not [s for s in sigs if isinstance(s, SweepPrint)]


def test_small_run_below_size_floor_is_not_a_sweep():
    e = OrderflowEngine()
    sigs = []
    for k in range(SWEEP_MIN_TICKS):
        sigs += e.process(_t(k * 10, price=7500.0 + k * TICK, size=5, side="B"))  # 15 << floor
    sigs += e.flush()
    assert not [s for s in sigs if isinstance(s, SweepPrint)]


def test_retrace_breaks_run():
    e = OrderflowEngine()
    sigs = []
    sigs += e.process(_t(0, price=7500.00, side="B"))
    sigs += e.process(_t(10, price=7500.25, side="B"))
    sigs += e.process(_t(20, price=7500.00, side="B"))  # not advancing: run resets
    sigs += e.flush()
    assert not [s for s in sigs if isinstance(s, SweepPrint)]


# ── divergence ──────────────────────────────────────────────────────────────
def _leg(e, sigs, start_ms, p0, p1, side, step_ms=400):
    """March price from p0 to p1 with the given aggressor side (slow: no sweeps)."""
    n = int(round(abs(p1 - p0) / TICK))
    d = TICK if p1 > p0 else -TICK
    for k in range(1, n + 1):
        sigs += e.process(_t(start_ms + k * step_ms, price=p0 + k * d, size=10, side=side))
    return start_ms + (n + 1) * step_ms


def test_bearish_divergence_new_high_weaker_cvd():
    e = OrderflowEngine()
    sigs: list = []
    F = PIVOT_FILTER_TICKS * TICK
    ms = _leg(e, sigs, 0, 7500.0, 7500.0 + 2 * F, "B")          # swing high 1, strong buying
    ms = _leg(e, sigs, ms, 7500.0 + 2 * F, 7500.0 + F, "A")     # confirm high; leg down
    ms = _leg(e, sigs, ms, 7500.0 + F, 7500.0 + 2 * F + TICK, "N")  # NEW high, zero delta behind it
    ms = _leg(e, sigs, ms, 7500.0 + 2 * F + TICK, 7500.0 + F, "A")  # confirm high 2
    div = [s for s in sigs if isinstance(s, DeltaDivergence)]
    assert len(div) == 1
    assert div[0].kind == "bearish"
    assert div[0].price_extreme > div[0].prior_extreme
    assert div[0].cvd_at_extreme < div[0].cvd_at_prior


def test_confirmed_higher_high_with_stronger_cvd_is_not_divergence():
    e = OrderflowEngine()
    sigs: list = []
    F = PIVOT_FILTER_TICKS * TICK
    ms = _leg(e, sigs, 0, 7500.0, 7500.0 + 2 * F, "B")
    ms = _leg(e, sigs, ms, 7500.0 + 2 * F, 7500.0 + F, "N")     # pullback on neutral flow
    ms = _leg(e, sigs, ms, 7500.0 + F, 7500.0 + 3 * F, "B")     # higher high, MORE buying
    ms = _leg(e, sigs, ms, 7500.0 + 3 * F, 7500.0 + 2 * F, "A")
    assert not [s for s in sigs if isinstance(s, DeltaDivergence)]


# ── determinism ─────────────────────────────────────────────────────────────
def test_double_run_identical():
    trades = [_t(i * 37, price=7500.0 + ((i * 7) % 23 - 11) * TICK,
                 size=(i % 17) + 1, side=["B", "A", "N", "B", "A"][i % 5])
              for i in range(2000)]
    a = OrderflowEngine().run(trades)
    b = OrderflowEngine().run(trades)
    assert a == b
