import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market.entities.trade import Trade
from market.orderflow.bars import build_bars

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 7, 2, 8, 30, 0, tzinfo=CENTRAL)


def _trade(i, price=7500.0, size=10, side="B"):
    return Trade(ts=T0 + timedelta(seconds=i), symbol="ES.c.0", instrument_id=1,
                 price=price, size=size, side=side, sequence=i)


def test_straddle_whole_trade_into_crossing_bar():
    # 3 x 40 = 120 with n=100: trade 3 crosses -> bar closes at 120, next bar empty
    trades = [_trade(i, size=40) for i in range(4)]
    bars = list(build_bars(trades, n=100, include_partial=True))
    assert [b.volume for b in bars] == [120, 40]


def test_none_side_in_volume_never_in_delta_or_cells():
    trades = [
        _trade(0, size=60, side="B"),
        _trade(1, size=30, side="N"),
        _trade(2, size=60, side="A"),
    ]
    (bar,) = build_bars(trades, n=150)
    assert bar.volume == 150
    assert bar.none_vol == 30
    assert bar.delta == 0                       # 60 buy − 60 sell; N excluded
    assert sum(c.total for c in bar.cells) == 120  # cells exclude N volume


def test_cells_accumulate_by_price_and_side():
    trades = [
        _trade(0, price=7500.0, size=10, side="B"),
        _trade(1, price=7500.0, size=5, side="A"),
        _trade(2, price=7500.25, size=7, side="B"),
        _trade(3, price=7500.0, size=3, side="B"),
    ]
    (bar,) = build_bars(trades, n=25)
    by_price = {c.price: c for c in bar.cells}
    assert by_price[7500.0].ask_vol == 13   # buy-aggressors lifted 10+3
    assert by_price[7500.0].bid_vol == 5    # sell-aggressor hit 5
    assert by_price[7500.25].ask_vol == 7
    assert bar.delta == 20 - 5


def test_ohlc_and_timestamps():
    trades = [
        _trade(0, price=7500.0), _trade(1, price=7502.0),
        _trade(2, price=7498.0), _trade(3, price=7501.0),
    ]
    (bar,) = build_bars(trades, n=40)
    assert (bar.open, bar.high, bar.low, bar.close) == (7500.0, 7502.0, 7498.0, 7501.0)
    assert bar.start_ts == trades[0].ts
    assert bar.end_ts == trades[-1].ts


def test_out_of_order_input_raises():
    trades = [_trade(5), _trade(3)]
    with pytest.raises(ValueError, match="out-of-order"):
        list(build_bars(trades, n=1000))


def test_partial_bar_only_when_asked():
    trades = [_trade(i, size=10) for i in range(5)]  # 50 contracts
    assert list(build_bars(trades, n=100)) == []
    bars = list(build_bars(trades, n=100, include_partial=True))
    assert len(bars) == 1 and bars[0].volume == 50


def test_double_run_is_identical():
    trades = [_trade(i, price=7500.0 + (i % 7) * 0.25, size=(i % 13) + 1,
                     side=["B", "A", "N"][i % 3]) for i in range(500)]
    a = list(build_bars(trades, n=200, include_partial=True))
    b = list(build_bars(trades, n=200, include_partial=True))
    assert a == b


def test_invalid_bar_size():
    with pytest.raises(ValueError, match="positive"):
        list(build_bars([], n=0))
