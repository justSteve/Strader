import pytest
from datetime import date
from market.entities.instrument import Contract
from market.entities.chain import Chain, strike_key

def _contract(strike: float, side: str) -> Contract:
    return Contract(
        symbol=f"SPXW260517{'C' if side == 'CALL' else 'P'}{int(strike * 10):08d}",
        underlying="$SPX", strike=strike, expiry=date(2026, 5, 17),
        contract_type=side,
        bid=10.0, ask=10.5, last=10.2, volume=100, open_interest=500,
        delta=0.3 if side == "CALL" else -0.3,
        gamma=0.01, theta=-5.0, vega=1.5, implied_volatility=14.0,
    )

def _chain():
    strikes = [5780.0, 5790.0, 5800.0, 5810.0, 5820.0]
    calls = {strike_key(s): _contract(s, "CALL") for s in strikes}
    puts  = {strike_key(s): _contract(s, "PUT")  for s in strikes}
    return Chain(
        underlying="$SPX", expiry=date(2026, 5, 17),
        calls=calls, puts=puts, underlying_price=5802.5,
    )

def test_strike_key_whole():
    assert strike_key(5800.0) == 58000

def test_strike_key_half():
    assert strike_key(5800.5) == 58005

def test_chain_call_lookup():
    c = _chain().call(5800.0)
    assert c.strike == 5800.0
    assert c.contract_type == "CALL"

def test_chain_put_lookup():
    p = _chain().put(5800.0)
    assert p.contract_type == "PUT"

def test_chain_missing_strike_raises():
    with pytest.raises(KeyError):
        _chain().call(9999.0)

def test_chain_nearest_call():
    c = _chain().nearest_call(5803.0)
    assert c.strike in (5800.0, 5810.0)

def test_chain_range():
    contracts = _chain().range(5790.0, 5810.0, "CALL")
    strikes = {c.strike for c in contracts}
    assert {5790.0, 5800.0, 5810.0} == strikes
