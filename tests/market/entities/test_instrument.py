import pytest
from datetime import date
from market.entities.instrument import Contract

def _contract(**kwargs):
    defaults = dict(
        symbol="SPXW  260517C05800000", underlying="$SPX",
        strike=5800.0, expiry=date(2026, 5, 17), contract_type="CALL",
        bid=22.5, ask=23.0, last=22.7,
        volume=1523, open_interest=4521,
        delta=0.42, gamma=0.012, theta=-8.5, vega=2.1, implied_volatility=14.8,
    )
    defaults.update(kwargs)
    return Contract(**defaults)

def test_contract_construction():
    c = _contract()
    assert c.strike == 5800.0
    assert c.contract_type == "CALL"
    assert c.delta == 0.42

def test_contract_is_frozen():
    c = _contract()
    with pytest.raises((AttributeError, TypeError)):
        c.bid = 25.0  # type: ignore

def test_contract_mid():
    c = _contract(bid=22.0, ask=24.0)
    assert c.mid == 23.0
