"""Trade builder endpoints."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.options_chain import _black_scholes_greeks

router = APIRouter(prefix="/api/trades", tags=["trades"])


class ButterflyRequest(BaseModel):
    center_strike: float
    width: float = 10.0
    quantity: int = 1
    expiration: str
    spot: float = 5800.0
    iv: float = 0.18


class VerticalRequest(BaseModel):
    long_strike: float
    short_strike: float
    option_type: str = "CALL"
    quantity: int = 1
    expiration: str
    spot: float = 5800.0
    iv: float = 0.18


@router.post("/butterfly/analyze")
async def analyze_butterfly(req: ButterflyRequest):
    """Analyze a butterfly spread — compute risk graph and greeks."""
    import math
    from datetime import datetime, timezone

    exp = datetime.fromisoformat(req.expiration).replace(tzinfo=timezone.utc)
    dte = max((exp - datetime.now(timezone.utc)).total_seconds() / 86400.0, 0.001)
    T = dte / 365.0

    lower = req.center_strike - req.width
    upper = req.center_strike + req.width

    lower_greeks = _black_scholes_greeks(req.spot, lower, T, 0.05, req.iv, "CALL")
    center_greeks = _black_scholes_greeks(req.spot, req.center_strike, T, 0.05, req.iv, "CALL")
    upper_greeks = _black_scholes_greeks(req.spot, upper, T, 0.05, req.iv, "CALL")

    # Butterfly: +1 lower, -2 center, +1 upper
    net_debit = lower_greeks["price"] - 2 * center_greeks["price"] + upper_greeks["price"]
    max_profit = req.width - abs(net_debit)
    max_loss = abs(net_debit)

    net_delta = lower_greeks["delta"] - 2 * center_greeks["delta"] + upper_greeks["delta"]
    net_gamma = lower_greeks["gamma"] - 2 * center_greeks["gamma"] + upper_greeks["gamma"]
    net_theta = lower_greeks["theta"] - 2 * center_greeks["theta"] + upper_greeks["theta"]
    net_vega = lower_greeks["vega"] - 2 * center_greeks["vega"] + upper_greeks["vega"]

    # Risk graph: PnL at expiration across price range
    risk_graph = []
    for price in range(int(lower - 30), int(upper + 31)):
        pnl_lower = max(0, price - lower)
        pnl_center = -2 * max(0, price - req.center_strike)
        pnl_upper = max(0, price - upper)
        pnl = (pnl_lower + pnl_center + pnl_upper - net_debit) * 100 * req.quantity
        risk_graph.append({"price": price, "pnl": round(pnl, 2)})

    return {
        "strategy": "BUTTERFLY",
        "legs": [
            {"strike": lower, "action": "BUY", "quantity": req.quantity, "type": "CALL"},
            {"strike": req.center_strike, "action": "SELL", "quantity": req.quantity * 2, "type": "CALL"},
            {"strike": upper, "action": "BUY", "quantity": req.quantity, "type": "CALL"},
        ],
        "net_debit": round(net_debit * 100 * req.quantity, 2),
        "max_profit": round(max_profit * 100 * req.quantity, 2),
        "max_loss": round(max_loss * 100 * req.quantity, 2),
        "breakevens": [round(lower + abs(net_debit), 2), round(upper - abs(net_debit), 2)],
        "greeks": {
            "delta": round(net_delta * req.quantity, 4),
            "gamma": round(net_gamma * req.quantity, 6),
            "theta": round(net_theta * req.quantity, 4),
            "vega": round(net_vega * req.quantity, 4),
        },
        "risk_graph": risk_graph,
        "dte": round(dte, 2),
    }


@router.post("/vertical/analyze")
async def analyze_vertical(req: VerticalRequest):
    """Analyze a vertical spread."""
    from datetime import datetime, timezone

    exp = datetime.fromisoformat(req.expiration).replace(tzinfo=timezone.utc)
    dte = max((exp - datetime.now(timezone.utc)).total_seconds() / 86400.0, 0.001)
    T = dte / 365.0

    long_greeks = _black_scholes_greeks(req.spot, req.long_strike, T, 0.05, req.iv, req.option_type)
    short_greeks = _black_scholes_greeks(req.spot, req.short_strike, T, 0.05, req.iv, req.option_type)

    net_debit = long_greeks["price"] - short_greeks["price"]
    width = abs(req.long_strike - req.short_strike)
    max_profit = (width - abs(net_debit)) if net_debit > 0 else abs(net_debit)
    max_loss = abs(net_debit) if net_debit > 0 else (width - abs(net_debit))

    net_delta = long_greeks["delta"] - short_greeks["delta"]
    net_gamma = long_greeks["gamma"] - short_greeks["gamma"]
    net_theta = long_greeks["theta"] - short_greeks["theta"]
    net_vega = long_greeks["vega"] - short_greeks["vega"]

    risk_graph = []
    low = int(min(req.long_strike, req.short_strike) - 30)
    high = int(max(req.long_strike, req.short_strike) + 31)
    for price in range(low, high):
        pnl_long = max(0, price - req.long_strike) if req.option_type == "CALL" else max(0, req.long_strike - price)
        pnl_short = -(max(0, price - req.short_strike) if req.option_type == "CALL" else max(0, req.short_strike - price))
        pnl = (pnl_long + pnl_short - net_debit) * 100 * req.quantity
        risk_graph.append({"price": price, "pnl": round(pnl, 2)})

    return {
        "strategy": "VERTICAL",
        "legs": [
            {"strike": req.long_strike, "action": "BUY", "quantity": req.quantity, "type": req.option_type},
            {"strike": req.short_strike, "action": "SELL", "quantity": req.quantity, "type": req.option_type},
        ],
        "net_debit": round(net_debit * 100 * req.quantity, 2),
        "max_profit": round(max_profit * 100 * req.quantity, 2),
        "max_loss": round(max_loss * 100 * req.quantity, 2),
        "greeks": {
            "delta": round(net_delta * req.quantity, 4),
            "gamma": round(net_gamma * req.quantity, 6),
            "theta": round(net_theta * req.quantity, 4),
            "vega": round(net_vega * req.quantity, 4),
        },
        "risk_graph": risk_graph,
        "dte": round(dte, 2),
    }
