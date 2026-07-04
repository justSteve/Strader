import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime
from zoneinfo import ZoneInfo

from market.entities.footprint import FootprintBar, FootprintCell

CENTRAL = ZoneInfo("America/Chicago")


def _ts(minute=0, second=0):
    return datetime(2026, 7, 2, 8, 30 + minute, second, tzinfo=CENTRAL)


def _bar(cells):
    return FootprintBar(
        symbol="ES.c.0", start_ts=_ts(), end_ts=_ts(0, 43),
        open=7500.0, high=7501.0, low=7499.5, close=7500.5,
        volume=sum(c.bid_vol + c.ask_vol for c in cells), delta=0, none_vol=0,
        cells=tuple(cells),
    )


def test_cell_totals_and_delta():
    c = FootprintCell(price=7500.0, bid_vol=120, ask_vol=380)
    assert c.total == 500
    assert c.delta == 260


def test_entities_are_frozen():
    c = FootprintCell(price=7500.0, bid_vol=1, ask_vol=1)
    with pytest.raises(FrozenInstanceError):
        c.bid_vol = 2
    b = _bar([c])
    with pytest.raises(FrozenInstanceError):
        b.volume = 99


def test_cells_must_be_ascending():
    cells = [FootprintCell(7500.25, 1, 1), FootprintCell(7500.0, 1, 1)]
    with pytest.raises(ValueError, match="ascending"):
        _bar(cells)


def test_duration_is_output_not_input():
    b = _bar([FootprintCell(7500.0, 1, 1)])
    assert b.duration_seconds == 43.0


def test_poc_lower_price_wins_tie():
    cells = [FootprintCell(7499.75, 100, 100), FootprintCell(7500.0, 150, 50)]
    b = _bar(cells)
    assert b.poc_price == 7499.75  # equal totals -> lower price
