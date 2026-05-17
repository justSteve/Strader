import json, pytest
from pathlib import Path
from datetime import date
from market.ingest import chain_from_schwab
from market.entities.spread import ButterflyTemplate, ButterflyInstance
from market.resolve import resolve_butterfly, ResolutionError

FIXTURE = Path(__file__).parent / "fixtures" / "schwab_chain_spx.json"

def _chain():
    return chain_from_schwab(json.loads(FIXTURE.read_text()), expiry=date(2026, 5, 17))

def test_resolve_atm():
    t = ButterflyTemplate(center="ATM", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert isinstance(result, ButterflyInstance)
    assert result.lower.strike < result.center.strike < result.upper.strike
    assert result.center.strike - result.lower.strike == 10.0
    assert result.upper.strike - result.center.strike == 10.0

def test_resolve_absolute_strike():
    t = ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert result.center.strike == 5800.0
    assert result.lower.strike == 5790.0
    assert result.upper.strike == 5810.0

def test_net_debit_positive():
    t = ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert result.net_debit > 0

def test_breakevens_bracket_center():
    t = ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert result.lower.strike < result.breakeven_lower < result.center.strike
    assert result.center.strike < result.breakeven_upper < result.upper.strike

def test_missing_strike_raises():
    t = ButterflyTemplate(center="5750", width=10, expiry="0DTE", contract_type="CALL")
    with pytest.raises(ResolutionError):
        resolve_butterfly(t, _chain())
