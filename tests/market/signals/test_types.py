import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from market.signals.types import Signal, Bias, Regime, Alert, Action, InferenceRequest

CENTRAL = ZoneInfo("America/Chicago")

def _ts():
    return datetime(2026, 5, 17, 9, 30, tzinfo=CENTRAL)

def test_bias_is_signal():
    b = Bias(timestamp=_ts(), source="gex_regime", confidence=0.8, reason="GEX negative", direction="bearish")
    assert isinstance(b, Signal)
    assert b.direction == "bearish"
    assert b.confidence == 0.8

def test_regime_is_signal():
    r = Regime(timestamp=_ts(), source="gex_regime", confidence=0.7, reason="compressed", state="compressed")
    assert isinstance(r, Signal)
    assert r.state == "compressed"

def test_alert_is_signal():
    a = Alert(timestamp=_ts(), source="position_risk", confidence=1.0, reason="delta exceeded", severity="warn", message="delta limit")
    assert a.severity == "warn"

def test_action_is_signal():
    act = Action(
        timestamp=_ts(), source="butterfly_entry", confidence=0.9, reason="conditions met",
        verb="enter_butterfly", params={"strike": 5800, "width": 5},
    )
    assert act.verb == "enter_butterfly"
    assert act.params["strike"] == 5800

def test_inference_request():
    req = InferenceRequest(
        timestamp=_ts(), source="footprint_context", confidence=0.0, reason="pattern unclear",
        context={"absorption_ratio": 2.5},
        question="Is this accumulation or distribution?",
        output_type="Bias",
    )
    assert req.output_type == "Bias"

def test_signal_timestamp_is_central():
    b = Bias(timestamp=_ts(), source="test", confidence=1.0, reason="test", direction="neutral")
    assert b.timestamp.tzinfo == CENTRAL

def test_dataclasses_are_frozen():
    b = Bias(timestamp=_ts(), source="test", confidence=1.0, reason="test", direction="neutral")
    with pytest.raises((AttributeError, TypeError)):
        b.direction = "bullish"  # type: ignore
