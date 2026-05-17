from datetime import datetime
from zoneinfo import ZoneInfo
from market.signals.types import Bias, Alert, Action
from present.signals import format_signals

CENTRAL = ZoneInfo("America/Chicago")

def _ts():
    return datetime(2026, 5, 17, 9, 45, tzinfo=CENTRAL)

def test_returns_string():
    assert isinstance(format_signals([]), str)

def test_empty_list():
    assert "no signals" in format_signals([]).lower()

def test_shows_bias():
    out = format_signals([
        Bias(timestamp=_ts(), source="gex_regime", confidence=0.8, reason="negative GEX", direction="bearish"),
    ])
    assert "bearish" in out.lower() or "BEARISH" in out

def test_shows_action():
    out = format_signals([
        Action(timestamp=_ts(), source="butterfly_entry", confidence=0.9, reason="conditions met",
               verb="enter_butterfly", params={"center": 5800, "width": 10}),
    ])
    assert "enter_butterfly" in out

def test_shows_multiple():
    signals = [
        Bias(timestamp=_ts(), source="gex", confidence=0.8, reason="negative GEX", direction="bearish"),
        Alert(timestamp=_ts(), source="risk", confidence=1.0, reason="delta limit", severity="warn", message="limit hit"),
    ]
    out = format_signals(signals)
    assert "bearish" in out.lower() or "BEARISH" in out
    assert "warn" in out.lower() or "WARN" in out
