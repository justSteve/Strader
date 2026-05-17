from datetime import date, datetime
from zoneinfo import ZoneInfo
from market.entities.session import Session
from market.entities.level import Level
from market.signals.types import Regime
from present.regime import format_regime

CENTRAL = ZoneInfo("America/Chicago")

def _session():
    return Session(
        date=date(2026, 5, 17), underlying_price=5820.5,
        open=5800.0, high=5840.0, low=5795.0,
        gex_posture="negative", vix=14.8,
        mancini_supports=(
            Level(price=5780.0, label="support", source="mancini"),
            Level(price=5750.0, label="support", source="mancini", annotation="major"),
        ),
        mancini_resistances=(Level(price=5850.0, label="resistance", source="mancini"),),
    )

def _regime():
    return Regime(
        timestamp=datetime(2026, 5, 17, 9, 45, tzinfo=CENTRAL),
        source="gex_regime", confidence=0.65,
        reason="Negative GEX + VIX 14.8: directional bias",
        state="trending",
    )

def test_returns_string():
    assert isinstance(format_regime(_regime(), _session()), str)

def test_contains_state():
    out = format_regime(_regime(), _session())
    assert "trending" in out.lower() or "TRENDING" in out

def test_contains_gex_posture():
    out = format_regime(_regime(), _session())
    assert "negative" in out.lower() or "NEG" in out.upper()

def test_contains_vix():
    out = format_regime(_regime(), _session())
    assert "14.8" in out

def test_contains_support_level():
    out = format_regime(_regime(), _session())
    assert "5780" in out or "5750" in out
