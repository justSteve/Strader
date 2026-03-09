"""Trade builder — construct butterflies and verticals with risk graphs."""
from __future__ import annotations

import math
from datetime import date

from app.models.schemas import (
    ButterflyOrder,
    VerticalSpreadOrder,
    OptionLeg,
    OptionType,
    Direction,
)


def build_butterfly(order: ButterflyOrder) -> dict:
    """Build a butterfly spread with P&L at expiration."""
    center = order.center_strike
    width = order.wing_width
    lower = center - width
    upper = center + width

    if order.option_type == OptionType.CALL:
        legs = [
            OptionLeg(
                symbol=f"SPXW {order.expiration.strftime('%y%m%d')}C{int(lower*1000):08d}",
                option_type=OptionType.CALL,
                strike=lower,
                expiration=order.expiration,
                direction=Direction.LONG,
                quantity=order.quantity,
            ),
            OptionLeg(
                symbol=f"SPXW {order.expiration.strftime('%y%m%d')}C{int(center*1000):08d}",
                option_type=OptionType.CALL,
                strike=center,
                expiration=order.expiration,
                direction=Direction.SHORT,
                quantity=order.quantity * 2,
            ),
            OptionLeg(
                symbol=f"SPXW {order.expiration.strftime('%y%m%d')}C{int(upper*1000):08d}",
                option_type=OptionType.CALL,
                strike=upper,
                expiration=order.expiration,
                direction=Direction.LONG,
                quantity=order.quantity,
            ),
        ]
    else:
        legs = [
            OptionLeg(
                symbol=f"SPXW {order.expiration.strftime('%y%m%d')}P{int(lower*1000):08d}",
                option_type=OptionType.PUT,
                strike=lower,
                expiration=order.expiration,
                direction=Direction.LONG,
                quantity=order.quantity,
            ),
            OptionLeg(
                symbol=f"SPXW {order.expiration.strftime('%y%m%d')}P{int(center*1000):08d}",
                option_type=OptionType.PUT,
                strike=center,
                expiration=order.expiration,
                direction=Direction.SHORT,
                quantity=order.quantity * 2,
            ),
            OptionLeg(
                symbol=f"SPXW {order.expiration.strftime('%y%m%d')}P{int(upper*1000):08d}",
                option_type=OptionType.PUT,
                strike=upper,
                expiration=order.expiration,
                direction=Direction.LONG,
                quantity=order.quantity,
            ),
        ]

    # Generate risk graph (P&L at expiration)
    risk_graph = _butterfly_risk_graph(lower, center, upper, width, order.quantity)

    return {
        "strategy": "BUTTERFLY",
        "legs": [leg.model_dump(mode="json") for leg in legs],
        "risk_graph": risk_graph,
        "max_profit": round(width * 100 * order.quantity, 2),
        "max_loss_estimate": round(width * 0.15 * 100 * order.quantity, 2),
        "breakeven_lower": round(lower + width * 0.15, 2),
        "breakeven_upper": round(upper - width * 0.15, 2),
    }


def build_vertical(order: VerticalSpreadOrder) -> dict:
    """Build a vertical spread with P&L at expiration."""
    is_debit = (
        (order.option_type == OptionType.CALL and order.long_strike < order.short_strike) or
        (order.option_type == OptionType.PUT and order.long_strike > order.short_strike)
    )
    width = abs(order.long_strike - order.short_strike)
    exp_str = order.expiration.strftime('%y%m%d')
    type_char = "C" if order.option_type == OptionType.CALL else "P"

    legs = [
        OptionLeg(
            symbol=f"SPXW {exp_str}{type_char}{int(order.long_strike*1000):08d}",
            option_type=order.option_type,
            strike=order.long_strike,
            expiration=order.expiration,
            direction=Direction.LONG,
            quantity=order.quantity,
        ),
        OptionLeg(
            symbol=f"SPXW {exp_str}{type_char}{int(order.short_strike*1000):08d}",
            option_type=order.option_type,
            strike=order.short_strike,
            expiration=order.expiration,
            direction=Direction.SHORT,
            quantity=order.quantity,
        ),
    ]

    risk_graph = _vertical_risk_graph(
        order.long_strike, order.short_strike, width, order.quantity, is_debit
    )

    return {
        "strategy": "VERTICAL",
        "spread_type": "DEBIT" if is_debit else "CREDIT",
        "legs": [leg.model_dump(mode="json") for leg in legs],
        "risk_graph": risk_graph,
        "width": width,
        "max_profit": round(width * 100 * order.quantity * (0.7 if is_debit else 0.3), 2),
        "max_loss": round(width * 100 * order.quantity * (0.3 if is_debit else 0.7), 2),
    }


def _butterfly_risk_graph(
    lower: float, center: float, upper: float, width: float, qty: int
) -> list[dict]:
    """Generate P&L points for butterfly at expiration."""
    points = []
    span = width * 3
    step = span / 100

    for i in range(101):
        price = lower - width + i * step
        # Butterfly P&L at expiration
        pnl_per = 0
        if price <= lower:
            pnl_per = 0  # Below lower wing
        elif price <= center:
            pnl_per = price - lower  # Rising to center
        elif price <= upper:
            pnl_per = upper - price  # Falling from center
        else:
            pnl_per = 0  # Above upper wing

        # Subtract debit paid (approximate)
        debit = width * 0.15
        pnl_per -= debit
        pnl = pnl_per * 100 * qty

        points.append({"price": round(price, 2), "pnl": round(pnl, 2)})

    return points


def _vertical_risk_graph(
    long_strike: float,
    short_strike: float,
    width: float,
    qty: int,
    is_debit: bool,
) -> list[dict]:
    """Generate P&L points for vertical at expiration."""
    points = []
    low = min(long_strike, short_strike) - width
    high = max(long_strike, short_strike) + width
    step = (high - low) / 100

    debit = width * 0.3 if is_debit else width * 0.7
    max_profit = (width - debit) * 100 * qty
    max_loss = debit * 100 * qty

    for i in range(101):
        price = low + i * step
        if is_debit:
            if price <= long_strike:
                pnl = -max_loss
            elif price >= short_strike:
                pnl = max_profit
            else:
                ratio = (price - long_strike) / width
                pnl = -max_loss + (max_profit + max_loss) * ratio
        else:
            if price <= short_strike:
                pnl = max_profit
            elif price >= long_strike:
                pnl = -max_loss
            else:
                ratio = (price - short_strike) / width
                pnl = max_profit - (max_profit + max_loss) * ratio

        points.append({"price": round(price, 2), "pnl": round(pnl, 2)})

    return points
