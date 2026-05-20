from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market.entities.trade import Trade

CENTRAL = ZoneInfo("America/Chicago")


def test_trade_construction():
    t = Trade(
        ts=datetime(2026, 5, 20, 9, 30, 0, tzinfo=CENTRAL),
        symbol="ES.c.0",
        instrument_id=42,
        price=5820.25,
        size=3,
        side="B",
    )
    assert t.symbol == "ES.c.0"
    assert t.price == 5820.25
    assert t.size == 3
    assert t.side == "B"
    assert t.instrument_id == 42


def test_trade_is_frozen():
    t = Trade(
        ts=datetime(2026, 5, 20, 9, 30, 0, tzinfo=CENTRAL),
        symbol="ES.c.0",
        instrument_id=42,
        price=5820.25,
        size=3,
    )
    with pytest.raises((AttributeError, TypeError)):
        t.price = 5821.0  # type: ignore


def test_trade_default_side_is_unknown():
    t = Trade(
        ts=datetime(2026, 5, 20, 9, 30, 0, tzinfo=CENTRAL),
        symbol="AAPL",
        instrument_id=1,
        price=200.0,
        size=100,
    )
    assert t.side == "N"
