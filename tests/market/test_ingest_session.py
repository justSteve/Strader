from datetime import date
from mancini.parser import Level as ManciniLevel, ManciniEmail
from market.ingest import session_from_mancini
from market.entities.session import Session
from market.entities.level import Level

def _email() -> ManciniEmail:
    return ManciniEmail(
        date="2026-05-17", subject="Mancini Daily",
        support_levels=[
            ManciniLevel(price=5780.0, annotation=""),
            ManciniLevel(price=5750.0, annotation="major"),
        ],
        resistance_levels=[ManciniLevel(price=5850.0, annotation="")],
        basic_themes="Range day likely",
    )

def _quote() -> dict:
    return {"mark": 5820.5, "openPrice": 5800.0, "highPrice": 5840.0, "lowPrice": 5795.0}

def test_session_returns_session():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    assert isinstance(s, Session)

def test_session_fields():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    assert s.date == date(2026, 5, 17)
    assert s.underlying_price == 5820.5
    assert s.gex_posture == "negative"
    assert s.vix == 14.8

def test_supports_bridged():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    assert len(s.mancini_supports) == 2
    assert all(isinstance(lev, Level) for lev in s.mancini_supports)
    assert s.mancini_supports[0].source == "mancini"

def test_major_annotation_preserved():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    major = next(l for l in s.mancini_supports if l.price == 5750.0)
    assert major.annotation == "major"

def test_session_no_regime():
    import dataclasses
    fields = {f.name for f in dataclasses.fields(Session)}
    assert "regime" not in fields
