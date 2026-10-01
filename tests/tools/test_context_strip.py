"""context_strip: RTH open is 08:30 CT in both DST regimes; the tape comes
through iter_trades. [st-epa3]"""
from __future__ import annotations

from datetime import date, datetime, timezone

from market.entities.trade import Trade
from tools import context_strip as cs


def test_rth_open_cdt_and_cst():
    assert cs.rth_open(date(2026, 10, 30)).astimezone(timezone.utc).hour == 13
    # after DST ends 2026-11-01 the cash open is 14:30 UTC, not 13:30
    after = cs.rth_open(date(2026, 11, 2)).astimezone(timezone.utc)
    assert (after.hour, after.minute) == (14, 30)


def _t(hh, mm, px, sz, side):
    ts = datetime(2026, 11, 2, hh, mm, tzinfo=timezone.utc).astimezone(cs.CT)
    return Trade(ts=ts, symbol="ESZ6", instrument_id=1, price=px, size=sz,
                 side=side, sequence=None)


def test_premarket_hour_after_dst_not_counted_as_rth():
    trades = [
        _t(13, 45, 6000.0, 10, "B"),   # 07:45 CST — premarket
        _t(14, 31, 6010.0, 2, "A"),    # 08:31 CST — RTH
    ]
    s = cs.tape_summary(trades, cs.rth_open(date(2026, 11, 2)))
    assert s["n_rth"] == 1
    assert s["cum_delta"] == -2
    assert s["pv"] / s["vol"] == 6010.0
    assert (s["day_lo"], s["day_hi"], s["last_px"]) == (6000.0, 6010.0, 6010.0)
