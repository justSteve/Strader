"""Level history as of a bar, from the tape [st-ygoz]."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from market.orderflow.fuel import FuelKnobs, FuelTracker
from market.orderflow.level_history import TapeLevelHistory
from runbook.mancini.schema import Level

T0 = datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)      # 08:30 CT


def tr(sec: float, price: float):
    return SimpleNamespace(ts=T0 + timedelta(seconds=sec), price=price, size=1)


def hist(**kw):
    return TapeLevelHistory([Level(price=7879.0, kind="resistance", source_quote="7879")],
                            window_start=T0, **kw)


def test_only_completed_candles_count_and_the_count_moves_with_the_bar():
    h = hist()
    h.add(tr(10, 7874.0))
    h.add(tr(60, 7878.5))           # 08:30 candle touches 7879 (±2) and closes under
    assert h.as_of(T0 + timedelta(seconds=120)) == {7879.0: {
        "n_touches": 0, "n_defenses": 0, "first_touch": None, "state": "untouched",
        "asof": None, "source": "tape"}}, "a forming candle says nothing yet"
    h.add(tr(310, 7870.0))          # next candle opens: the 08:30 candle is complete
    r = h.as_of(T0 + timedelta(seconds=310))[7879.0]
    assert (r["n_touches"], r["n_defenses"], r["state"]) == (1, 1, "tested-held")
    assert r["asof"] == (T0 + timedelta(minutes=5)).isoformat()
    h.add(tr(400, 7882.0))          # 08:35 candle closes through: broken
    h.add(tr(610, 7880.0))
    r2 = h.as_of(T0 + timedelta(seconds=610))[7879.0]
    assert r2["state"] == "broken" and r2["n_touches"] == 2
    # asking about an EARLIER bar still gets the earlier answer — as of, not latest
    assert h.as_of(T0 + timedelta(seconds=310))[7879.0]["state"] == "tested-held"


def test_trades_before_the_letter_window_are_ignored():
    h = hist()
    h.add(SimpleNamespace(ts=T0 - timedelta(minutes=30), price=7879.0, size=1))
    h.add(tr(310, 7870.0))
    assert h.as_of(T0 + timedelta(minutes=10))[7879.0]["n_touches"] == 0


def test_fuel_prints_the_as_of_history_with_its_provenance():
    h = hist()
    for s, p in [(10, 7876.0), (60, 7878.5), (310, 7876.0)]:
        h.add(tr(s, p))
    fuel = FuelTracker([7879.0], history_fn=h.as_of, knobs=FuelKnobs(refresh_bars=1))
    bar = SimpleNamespace(start_ts=T0 + timedelta(seconds=300), end_ts=T0 + timedelta(seconds=320),
                          open=7876.0, high=7877.0, low=7875.5, close=7876.0, volume=2000,
                          delta=0, cells=[])
    ev = fuel.on_bar(bar)
    assert ev and "touched 1x / defended 1x" in ev["reason"] and "untouched" not in ev["reason"]
    assert ev["history"]["source"] == "tape" and ev["history"]["asof"]
