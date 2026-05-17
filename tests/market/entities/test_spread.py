import pytest
from datetime import date
from market.entities.instrument import Contract
from market.entities.spread import ButterflyTemplate, ButterflyInstance

def _contract(strike: float) -> Contract:
    return Contract(
        symbol=f"SPXW260517C{int(strike)}000", underlying="$SPX",
        strike=strike, expiry=date(2026, 5, 17), contract_type="CALL",
        bid=10.0, ask=10.5, last=10.2, volume=100, open_interest=500,
        delta=0.3, gamma=0.01, theta=-5.0, vega=1.5, implied_volatility=14.0,
    )

def _instance() -> ButterflyInstance:
    return ButterflyInstance(
        template=ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL"),
        lower=_contract(5790.0),
        center=_contract(5800.0),
        upper=_contract(5810.0),
        net_debit=2.5, max_profit=7.5, max_loss=2.5,
        breakeven_lower=5792.5, breakeven_upper=5807.5,
    )

def test_butterfly_template():
    t = ButterflyTemplate(center="ATM", width=5, expiry="0DTE", contract_type="CALL")
    assert t.center == "ATM"
    assert t.width == 5

def test_butterfly_template_is_frozen():
    t = ButterflyTemplate(center="ATM", width=5, expiry="0DTE", contract_type="CALL")
    with pytest.raises((AttributeError, TypeError)):
        t.width = 10  # type: ignore

def test_butterfly_instance():
    inst = _instance()
    assert inst.net_debit == 2.5
    assert inst.max_profit == 7.5
    assert inst.center.strike == 5800.0

def test_butterfly_instance_is_frozen():
    inst = _instance()
    with pytest.raises((AttributeError, TypeError)):
        inst.net_debit = 3.0  # type: ignore
