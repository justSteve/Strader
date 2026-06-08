"""Offline tests for the Schwab corpus stream. [st-1yp]

No live Schwab API, no credentials, no gate key: `create_client` is
monkeypatched with a fake (or the repo's MockSchwabClient) so pull_cycle's
quote/basis/straddle derivation and error handling are exercised purely
offline. Closes the coverage gap on the Schwab polling path.
"""
from __future__ import annotations

import pytest

from market.corpus import schwab_stream


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, quotes, chain, *, fail_quotes=False, fail_chain=False):
        self._quotes = quotes
        self._chain = chain
        self._fail_quotes = fail_quotes
        self._fail_chain = fail_chain

    def get_quotes(self, symbols):
        if self._fail_quotes:
            raise RuntimeError("quotes boom")
        return FakeResp(self._quotes)

    def get_option_chain(self, **kwargs):
        if self._fail_chain:
            raise RuntimeError("chain boom")
        return FakeResp(self._chain)


QUOTES = {
    "$SPX": {"quote": {
        "lastPrice": 5500.0, "openPrice": 5490.0, "highPrice": 5510.0,
        "lowPrice": 5485.0, "closePrice": 5495.0, "netChange": 5.0,
        "netPercentChange": 0.09, "quoteTime": 1717000000,
    }},
    "/ES:XCME": {"quote": {
        "lastPrice": 5512.25, "openPrice": 5500.0, "highPrice": 5520.0,
        "lowPrice": 5498.0, "closePrice": 5505.0, "bidPrice": 5512.0,
        "askPrice": 5512.5, "quoteTime": 1717000001,
    }},
}

CHAIN = {
    "status": "SUCCESS",
    "underlyingPrice": 5500.0,
    "interestRate": 4.5,
    "callExpDateMap": {"2026-06-08:0": {
        "5500.0": [{"mark": 12.0, "bid": 11.8, "ask": 12.2, "volatility": 15.0,
                    "delta": 0.50, "openInterest": 100, "totalVolume": 2000}],
        "5510.0": [{"mark": 7.0, "bid": 6.8, "ask": 7.2, "volatility": 14.0,
                    "delta": 0.38, "openInterest": 50, "totalVolume": 800}],
    }},
    "putExpDateMap": {"2026-06-08:0": {
        "5500.0": [{"mark": 11.5, "bid": 11.3, "ask": 11.7, "volatility": 16.0,
                    "delta": -0.50, "openInterest": 90, "totalVolume": 1800}],
        "5490.0": [{"mark": 7.5, "bid": 7.3, "ask": 7.7, "volatility": 17.0,
                    "delta": -0.39, "openInterest": 60, "totalVolume": 900}],
    }},
}


def test_pull_cycle_derives_spot_basis_and_straddle(monkeypatch):
    monkeypatch.setattr(schwab_stream, "create_client",
                        lambda: FakeClient(QUOTES, CHAIN))
    rec = schwab_stream.pull_cycle("$SPX")

    assert rec["stream"] == "schwab"
    assert rec["errors"] == []
    d = rec["data"]
    assert d["spot_spx"] == 5500.0
    assert d["spot_es"] == 5512.25
    assert d["es_minus_spx_basis"] == pytest.approx(12.25)
    # ATM = closest overlapping strike to spot (5500), straddle = call+put mark
    assert d["atm"]["atm_strike"] == 5500.0
    assert d["atm"]["atm_straddle"] == pytest.approx(23.5)
    # ±-window carries both sides
    sides = {row["side"] for row in d["chain_window"]}
    assert sides == {"CALL", "PUT"}


def test_pull_cycle_captures_quote_error_without_crashing(monkeypatch):
    monkeypatch.setattr(schwab_stream, "create_client",
                        lambda: FakeClient(QUOTES, CHAIN, fail_quotes=True))
    rec = schwab_stream.pull_cycle("$SPX")

    assert any("get_quotes" in e for e in rec["errors"])
    assert rec["data"]["spot_spx"] is None          # no quote -> no spot
    assert rec["data"]["atm"] == {}                 # no spot -> ATM skipped


def test_pull_cycle_with_repo_mock_client(monkeypatch):
    """Integration with the repo's MockSchwabClient + its fixtures — proves
    pull_cycle survives the real fixture shapes end to end."""
    from broker_schwab.mock.client import create_mock_client
    monkeypatch.setattr(schwab_stream, "create_client", create_mock_client)
    rec = schwab_stream.pull_cycle("$SPX")

    assert rec["stream"] == "schwab"
    assert isinstance(rec["errors"], list)
    assert "atm" in rec["data"]
    assert isinstance(rec["data"]["chain_window"], list)
