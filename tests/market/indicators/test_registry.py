from datetime import date, datetime
from zoneinfo import ZoneInfo
from market.entities.session import Session
from market.signals.types import Signal, Bias, Regime
from market.indicators.registry import indicator, run_indicators, _REGISTRY

CENTRAL = ZoneInfo("America/Chicago")

def _session() -> Session:
    return Session(
        date=date(2026, 5, 17), underlying_price=5820.5,
        open=5800.0, high=5840.0, low=5795.0,
        gex_posture="negative", vix=14.8,
        mancini_supports=(), mancini_resistances=(),
    )

def _ts():
    return datetime(2026, 5, 17, 9, 30, tzinfo=CENTRAL)

def test_indicator_registers():
    initial = len(_REGISTRY)

    @indicator(inputs=["Chain", "Session"], output="Bias", name="test_reg_bias")
    def _f(chain, session) -> Bias:
        return Bias(timestamp=_ts(), source="test_reg_bias", confidence=0.8, reason="test", direction="bullish")

    assert len(_REGISTRY) == initial + 1
    assert _REGISTRY[-1].name == "test_reg_bias"

def test_run_indicators_returns_signals():
    @indicator(inputs=["Session"], output="Regime", name="test_reg_regime")
    def _f(chain, session) -> Regime:
        return Regime(timestamp=_ts(), source="test_reg_regime", confidence=0.7, reason="test", state="ranging")

    signals = run_indicators(chain=None, session=_session())
    assert any(isinstance(s, Regime) for s in signals)

def test_all_results_are_signals():
    signals = run_indicators(chain=None, session=_session())
    for s in signals:
        assert isinstance(s, Signal), f"Expected Signal, got {type(s)}"
