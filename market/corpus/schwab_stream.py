"""Schwab stream pull — one cycle. [st-1yp]

Pulls spot quotes (SPX, /ES), 0DTE ATM ±10 chain, derives ATM straddle
and basis. Returns a dict ready to write via market.corpus.writer.

Imported by both `scripts/corpus_pull_schwab.py` (CLI shim) and
`scripts/corpus_poll.py` (orchestrator).
"""
from __future__ import annotations

from datetime import date as _date

from broker_schwab.client import create_client

from .writer import utc_now_iso


def _extract_atm(chain: dict, target_spot: float) -> dict:
    call_map = chain.get("callExpDateMap", {})
    put_map = chain.get("putExpDateMap", {})
    if not call_map or not put_map:
        return {"atm_strike": None, "reason": "empty 0DTE chain maps"}

    call_exp = next(iter(call_map))
    put_exp = next(iter(put_map))
    strikes = sorted(
        {float(k) for k in call_map[call_exp]} & {float(k) for k in put_map[put_exp]},
        key=lambda k: abs(k - target_spot),
    )
    if not strikes:
        return {"atm_strike": None, "reason": "no overlapping call/put strikes"}

    atm_k = strikes[0]
    call_key = f"{atm_k:.1f}"
    put_key = f"{atm_k:.1f}"
    if call_key not in call_map[call_exp] or put_key not in put_map[put_exp]:
        return {"atm_strike": atm_k, "reason": "strike format mismatch in chain dict"}
    call = call_map[call_exp][call_key][0]
    put = put_map[put_exp][put_key][0]

    call_mark = call.get("mark")
    put_mark = put.get("mark")
    return {
        "atm_strike": atm_k,
        "atm_call_mark": call_mark,
        "atm_put_mark": put_mark,
        "atm_straddle": (call_mark + put_mark) if (call_mark is not None and put_mark is not None) else None,
        "atm_call_iv": call.get("volatility"),
        "atm_put_iv": put.get("volatility"),
        "atm_call_delta": call.get("delta"),
        "atm_put_delta": put.get("delta"),
        "atm_call_oi": call.get("openInterest"),
        "atm_put_oi": put.get("openInterest"),
        "atm_call_vol": call.get("totalVolume"),
        "atm_put_vol": put.get("totalVolume"),
        "expiry_call": call_exp,
        "expiry_put": put_exp,
    }


def _strikes_window(chain: dict, n: int = 10) -> list[dict]:
    rows: list[dict] = []
    for side_label, side_key in (("CALL", "callExpDateMap"), ("PUT", "putExpDateMap")):
        m = chain.get(side_key, {})
        if not m:
            continue
        exp = next(iter(m))
        for k_str, contracts in m[exp].items():
            for c in contracts:
                rows.append({
                    "strike": float(k_str),
                    "side": side_label,
                    "bid": c.get("bid"),
                    "ask": c.get("ask"),
                    "mark": c.get("mark"),
                    "iv": c.get("volatility"),
                    "delta": c.get("delta"),
                    "oi": c.get("openInterest"),
                    "vol": c.get("totalVolume"),
                })
    return rows


def pull_cycle(symbol: str = "$SPX") -> dict:
    """Run one Schwab corpus pull. Returns the JSONL-ready record."""
    ts_pull = utc_now_iso()
    client = create_client()
    errors: list[str] = []

    quotes_data: dict = {}
    try:
        r = client.get_quotes([symbol, "/ES"])
        r.raise_for_status()
        quotes_data = r.json()
    except Exception as e:
        errors.append(f"get_quotes: {type(e).__name__}: {e}")

    spx_quote = quotes_data.get(symbol, {}).get("quote", {}) if quotes_data else {}
    es_key = next((k for k in quotes_data if k.startswith("/ES")), None) if quotes_data else None
    es_quote = quotes_data.get(es_key, {}).get("quote", {}) if es_key else {}

    spot_spx = spx_quote.get("lastPrice") or spx_quote.get("mark")
    spot_es = es_quote.get("lastPrice") or es_quote.get("mark")
    basis = (spot_es - spot_spx) if (spot_spx is not None and spot_es is not None) else None

    chain_data: dict = {}
    try:
        r = client.get_option_chain(
            symbol=symbol,
            strike_count=20,
            from_date=_date.today(),
            to_date=_date.today(),
            include_underlying_quote=True,
        )
        r.raise_for_status()
        chain_data = r.json()
    except Exception as e:
        errors.append(f"get_option_chain: {type(e).__name__}: {e}")

    atm = _extract_atm(chain_data, spot_spx) if (spot_spx and chain_data) else {}

    return {
        "ts_pull_utc": ts_pull,
        "stream": "schwab",
        "provenance": {
            "endpoints": ["get_quotes", "get_option_chain"],
            "symbol": symbol,
            "ts_spx_quote": spx_quote.get("quoteTime") or spx_quote.get("tradeTime"),
            "ts_es_quote": es_quote.get("quoteTime") or es_quote.get("tradeTime"),
        },
        "data": {
            "spot_spx": spot_spx,
            "spot_es": spot_es,
            "es_minus_spx_basis": basis,
            "spx_session_open": spx_quote.get("openPrice"),
            "spx_session_high": spx_quote.get("highPrice"),
            "spx_session_low": spx_quote.get("lowPrice"),
            "spx_prior_close": spx_quote.get("closePrice"),
            "spx_net_change": spx_quote.get("netChange"),
            "spx_net_pct_change": spx_quote.get("netPercentChange"),
            "es_session_open": es_quote.get("openPrice"),
            "es_session_high": es_quote.get("highPrice"),
            "es_session_low": es_quote.get("lowPrice"),
            "es_prior_close": es_quote.get("closePrice"),
            "es_bid": es_quote.get("bidPrice"),
            "es_ask": es_quote.get("askPrice"),
            "atm": atm,
            "chain_window": _strikes_window(chain_data, n=10),
            "chain_status": chain_data.get("status"),
            "chain_underlying_price": chain_data.get("underlyingPrice"),
            "chain_interest_rate": chain_data.get("interestRate"),
        },
        "errors": errors,
    }
