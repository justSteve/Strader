import json
from pathlib import Path
from datetime import date
from market.ingest import chain_from_schwab
from market.entities.chain import Chain, strike_key
from market.entities.instrument import Contract

FIXTURE = Path(__file__).parent / "fixtures" / "schwab_chain_spx.json"

def _data():
    return json.loads(FIXTURE.read_text())

def test_chain_from_schwab_returns_chain():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert isinstance(chain, Chain)

def test_chain_underlying():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert chain.underlying == "$SPX"
    assert chain.underlying_price == 5820.5

def test_chain_calls_indexed_by_int_key():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert strike_key(5800.0) in chain.calls
    c = chain.call(5800.0)
    assert isinstance(c, Contract)
    assert c.strike == 5800.0
    assert c.contract_type == "CALL"
    assert c.delta == 0.42

def test_chain_puts_indexed_by_int_key():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    p = chain.put(5800.0)
    assert p.contract_type == "PUT"
    assert p.delta == -0.58

def test_no_float_keys():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    for k in chain.calls:
        assert isinstance(k, int), f"Expected int key, got {type(k)}: {k}"
    for k in chain.puts:
        assert isinstance(k, int), f"Expected int key, got {type(k)}: {k}"

def test_contract_symbol_preserved():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert chain.call(5810.0).symbol == "SPXW  260517C05810000"
