import dataclasses
import pytest
from datetime import date
from market.entities.session import Session
from market.entities.level import Level

def _supports():
    return (
        Level(price=5780.0, label="support", source="mancini"),
        Level(price=5750.0, label="support", source="mancini", annotation="major"),
    )

def test_session_construction():
    s = Session(
        date=date(2026, 5, 17),
        underlying_price=5820.5,
        open=5800.0,
        high=5840.0,
        low=5795.0,
        gex_posture="negative",
        vix=14.8,
        mancini_supports=_supports(),
        mancini_resistances=(Level(price=5850.0, label="resistance", source="mancini"),),
    )
    assert s.underlying_price == 5820.5
    assert s.gex_posture == "negative"
    assert len(s.mancini_supports) == 2

def test_session_is_frozen():
    s = Session(
        date=date(2026, 5, 17), underlying_price=5820.5, open=5800.0,
        high=5840.0, low=5795.0, gex_posture="negative", vix=14.8,
        mancini_supports=(), mancini_resistances=(),
    )
    with pytest.raises((AttributeError, TypeError)):
        s.underlying_price = 5830.0  # type: ignore

def test_session_has_no_regime_or_opening_range():
    field_names = {f.name for f in dataclasses.fields(Session)}
    assert "regime" not in field_names, "Session must not carry regime — produced by indicator"
    assert "opening_range" not in field_names, "Session must not carry opening_range — produced by orb indicator"
