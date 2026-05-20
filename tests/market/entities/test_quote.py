from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market.entities.quote import Quote

CENTRAL = ZoneInfo("America/Chicago")


def _quote(**overrides) -> Quote:
    defaults = dict(
        ts=datetime(2026, 5, 20, 9, 30, 0, tzinfo=CENTRAL),
        symbol="AAPL",
        instrument_id=42,
        bid_price=298.50,
        bid_size=100,
        ask_price=298.55,
        ask_size=200,
    )
    defaults.update(overrides)
    return Quote(**defaults)


def test_quote_construction():
    q = _quote()
    assert q.symbol == "AAPL"
    assert q.bid_price == 298.50
    assert q.ask_price == 298.55
    assert q.bid_size == 100
    assert q.ask_size == 200


def test_quote_is_frozen():
    q = _quote()
    with pytest.raises((AttributeError, TypeError)):
        q.bid_price = 299.00  # type: ignore


def test_quote_mid():
    q = _quote(bid_price=100.0, ask_price=100.10)
    assert q.mid == pytest.approx(100.05)


def test_quote_spread():
    q = _quote(bid_price=100.0, ask_price=100.10)
    assert q.spread == pytest.approx(0.10)
