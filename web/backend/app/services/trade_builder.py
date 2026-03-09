"""Trade builder — butterfly constructor, spread builder, risk graph."""

import math
from datetime import date

from ..schemas.options import (
    SpreadLeg, TradeSetup, TradeEvaluation, RiskGraphPoint,
)


def build_butterfly(
    center_strike: float,
    width: float,
    expiration: date,
    option_type: str = "CALL",
    prices: dict[float, float] | None = None,
) -> TradeSetup:
    """Build a butterfly spread."""
    lower = center_strike - width
    upper = center_strike + width

    legs = [
        SpreadLeg(strike=lower, option_type=option_type, action="BUY", quantity=1,
                  price=prices.get(lower) if prices else None),
        SpreadLeg(strike=center_strike, option_type=option_type, action="SELL", quantity=2,
                  price=prices.get(center_strike) if prices else None),
        SpreadLeg(strike=upper, option_type=option_type, action="BUY", quantity=1,
                  price=prices.get(upper) if prices else None),
    ]

    # Calculate max risk/reward from prices if available
    max_risk = None
    max_reward = None
    if prices and all(prices.get(s) is not None for s in [lower, center_strike, upper]):
        debit = prices[lower] - 2 * prices[center_strike] + prices[upper]
        max_risk = abs(debit) * 100
        max_reward = (width - abs(debit)) * 100

    breakevens = [lower + abs(debit) if max_risk else lower, upper - abs(debit) if max_risk else upper] if max_risk else []

    return TradeSetup(
        strategy="butterfly",
        direction="long",
        legs=legs,
        expiration=expiration,
        max_risk=max_risk,
        max_reward=max_reward,
        breakevens=breakevens,
    )


def build_vertical(
    long_strike: float,
    short_strike: float,
    expiration: date,
    option_type: str = "CALL",
    prices: dict[float, float] | None = None,
) -> TradeSetup:
    """Build a vertical spread."""
    is_debit = (option_type == "CALL" and long_strike < short_strike) or \
               (option_type == "PUT" and long_strike > short_strike)

    legs = [
        SpreadLeg(strike=long_strike, option_type=option_type, action="BUY", quantity=1,
                  price=prices.get(long_strike) if prices else None),
        SpreadLeg(strike=short_strike, option_type=option_type, action="SELL", quantity=1,
                  price=prices.get(short_strike) if prices else None),
    ]

    max_risk = None
    max_reward = None
    width = abs(long_strike - short_strike)

    if prices and prices.get(long_strike) is not None and prices.get(short_strike) is not None:
        net = prices[long_strike] - prices[short_strike]
        if is_debit:
            max_risk = abs(net) * 100
            max_reward = (width - abs(net)) * 100
        else:
            max_risk = (width - abs(net)) * 100
            max_reward = abs(net) * 100

    return TradeSetup(
        strategy="vertical",
        direction="long" if is_debit else "short",
        legs=legs,
        expiration=expiration,
        max_risk=max_risk,
        max_reward=max_reward,
    )


def evaluate_trade(setup: TradeSetup, underlying_price: float) -> TradeEvaluation:
    """Evaluate a trade setup and generate risk graph."""
    risk_graph = _generate_risk_graph(setup, underlying_price)

    max_profit = max(p.pnl for p in risk_graph)
    max_loss = min(p.pnl for p in risk_graph)

    risk_reward = abs(max_profit / max_loss) if max_loss != 0 else float("inf")

    rejection_reasons = []
    if setup.max_risk and setup.max_risk > 5000:
        rejection_reasons.append("Max risk exceeds $5,000 notional limit")
    if risk_reward < 0.5:
        rejection_reasons.append("Risk/reward ratio below 0.5")

    return TradeEvaluation(
        setup=setup,
        risk_graph=risk_graph,
        max_profit=max_profit,
        max_loss=max_loss,
        risk_reward_ratio=round(risk_reward, 2),
        passes_criteria=len(rejection_reasons) == 0,
        rejection_reasons=rejection_reasons,
    )


def _generate_risk_graph(
    setup: TradeSetup, underlying_price: float, points: int = 50
) -> list[RiskGraphPoint]:
    """Generate P&L at expiration across price range."""
    strikes = [leg.strike for leg in setup.legs]
    min_strike = min(strikes)
    max_strike = max(strikes)
    spread = max_strike - min_strike

    start = min_strike - spread * 0.5
    end = max_strike + spread * 0.5
    step = (end - start) / points

    graph = []
    for i in range(points + 1):
        price = start + step * i
        pnl = 0

        for leg in setup.legs:
            if leg.option_type == "CALL":
                intrinsic = max(price - leg.strike, 0)
            else:
                intrinsic = max(leg.strike - price, 0)

            leg_price = leg.price or 0
            if leg.action == "BUY":
                pnl += (intrinsic - leg_price) * leg.quantity * 100
            else:
                pnl += (leg_price - intrinsic) * leg.quantity * 100

        graph.append(RiskGraphPoint(price=round(price, 2), pnl=round(pnl, 2)))

    return graph
