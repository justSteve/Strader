"""Risk engine — continuous monitoring and alerts."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session
from ..core.redis import redis_client
from ..models.trade import RiskLimit, Alert
from ..schemas.options import RiskAlert
from .positions import get_positions, get_portfolio_greeks

logger = logging.getLogger(__name__)


async def check_risk_limits() -> list[RiskAlert]:
    """Check all risk limits and return any breaches."""
    alerts = []

    async with async_session() as session:
        result = await session.execute(select(RiskLimit))
        limits = {r.limit_name: r for r in result.scalars().all()}

    greeks = await get_portfolio_greeks()
    positions = await get_positions()

    checks = {
        "max_portfolio_delta": abs(greeks.total_delta),
        "max_portfolio_gamma": abs(greeks.total_gamma),
        "max_position_count": len(positions),
        "max_single_position": max(
            (abs(p.market_value or 0) for p in positions), default=0
        ),
    }

    # Check daily PnL from positions
    daily_pnl = sum(p.pnl_day or 0 for p in positions)
    max_daily_loss_limit = limits.get("max_daily_loss")
    if max_daily_loss_limit and daily_pnl < float(max_daily_loss_limit.limit_value):
        alerts.append(RiskAlert(
            alert_type="max_daily_loss",
            severity="critical",
            message=f"[ALERT] Daily P&L ${daily_pnl:.2f} breached limit ${max_daily_loss_limit.limit_value}",
            current_value=daily_pnl,
            limit_value=float(max_daily_loss_limit.limit_value),
            breached=True,
        ))

    for limit_name, current_value in checks.items():
        limit = limits.get(limit_name)
        if not limit:
            continue

        breached = current_value > float(limit.limit_value)
        if breached:
            alerts.append(RiskAlert(
                alert_type=limit_name,
                severity="warning" if current_value < float(limit.limit_value) * 1.2 else "critical",
                message=f"[ALERT] {limit_name}: {current_value:.2f} exceeds limit {limit.limit_value}",
                current_value=current_value,
                limit_value=float(limit.limit_value),
                breached=True,
            ))

        # Update current value in DB
        async with async_session() as session:
            await session.execute(
                update(RiskLimit)
                .where(RiskLimit.limit_name == limit_name)
                .values(current_value=current_value, breached=breached, updated_at=datetime.now(timezone.utc))
            )
            await session.commit()

    # Persist critical alerts
    if any(a.severity == "critical" for a in alerts):
        async with async_session() as session:
            for alert in alerts:
                if alert.severity == "critical":
                    session.add(Alert(
                        alert_type=alert.alert_type,
                        severity=alert.severity,
                        message=alert.message,
                        data={"current": alert.current_value, "limit": alert.limit_value},
                    ))
            await session.commit()

    # Cache alerts for WebSocket broadcast
    import json
    await redis_client.setex(
        "risk:alerts",
        10,
        json.dumps([a.model_dump() for a in alerts]),
    )

    return alerts


async def get_cached_alerts() -> list[RiskAlert]:
    """Get cached risk alerts."""
    import json
    cached = await redis_client.get("risk:alerts")
    if cached:
        return [RiskAlert.model_validate(a) for a in json.loads(cached)]
    return []
