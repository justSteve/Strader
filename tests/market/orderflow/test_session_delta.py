"""The page's Session Δ is the engine's CVD — one number. [st-v69l]"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market.entities.trade import Trade
from market.orderflow.bars import build_bars
from market.orderflow.fill import bar_trade_slices, session_delta
from market.orderflow.replay import has_es_day, read_corpus_day

CT = ZoneInfo("America/Chicago")


def _t(hh, mm, size, side, day=date(2026, 9, 30)):
    return Trade(ts=datetime(day.year, day.month, day.day, hh, mm, tzinfo=CT),
                 symbol="ESZ6", instrument_id=1, price=7700.0, size=size, side=side)


def test_a_bar_straddling_the_open_counts_only_its_post_open_trades():
    trades = [_t(8, 29, 50, "A"), _t(8, 30, 7, "B"), _t(8, 31, 3, "A")]
    assert session_delta(trades, date(2026, 9, 30)) == 4


def test_after_midnight_still_counts_until_the_next_open():
    nxt = date(2026, 10, 1)
    assert session_delta([_t(0, 5, 9, "B", day=nxt)], date(2026, 9, 30)) == 9


@pytest.mark.skipif(not has_es_day(date(2026, 9, 30)), reason="corpus day absent")
def test_the_sum_over_a_day_is_the_engines_cvd():
    import market.orderflow.engine as eng
    d = date(2026, 9, 30)
    trades = read_corpus_day(d)
    bars = list(build_bars(trades, n=2000, include_partial=True))
    page = sum(session_delta(sl, d) for sl in bar_trade_slices(trades, bars))
    e = eng.OrderflowEngine()
    for t in trades:
        e.process(t)
    assert page == e.cvd
