"""Risk engine — monitors portfolio against risk limits."""
from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.models.schemas import RiskStatus, Alert
from app.services.account import account_service

logger = logging.getLogger(__name__)


class RiskEngine:
    async def get_risk_status(self) -> RiskStatus:
        """Evaluate current portfolio against risk limits."""
        positions = await account_service.get_positions()
        greeks = await account_service.get_portfolio_greeks()
        balance = await account_service.get_account_balance()

        day_pnl = sum(p.day_pnl for p in positions)
        daily_limit = settings.max_daily_loss

        # Max single position check
        max_single = max((abs(p.market_value) for p in positions), default=0)

        breaches: list[str] = []
        warnings: list[str] = []

        # Daily loss check
        if abs(day_pnl) > daily_limit:
            breaches.append(f"Daily loss ${abs(day_pnl):.0f} exceeds limit ${daily_limit:.0f}")
        elif abs(day_pnl) > daily_limit * 0.8:
            warnings.append(f"Daily loss at {abs(day_pnl)/daily_limit*100:.0f}% of limit")

        # Position count
        if len(positions) > settings.max_position_count:
            breaches.append(f"Position count {len(positions)} exceeds max {settings.max_position_count}")
        elif len(positions) > settings.max_position_count * 0.8:
            warnings.append(f"Position count at {len(positions)}/{settings.max_position_count}")

        # Single position size
        if max_single > settings.max_single_position_size:
            breaches.append(f"Position ${max_single:.0f} exceeds max ${settings.max_single_position_size:.0f}")

        # Portfolio delta
        if abs(greeks.total_delta) > settings.max_portfolio_delta:
            breaches.append(f"Portfolio delta {greeks.total_delta:.1f} exceeds max {settings.max_portfolio_delta}")
        elif abs(greeks.total_delta) > settings.max_portfolio_delta * 0.7:
            warnings.append(f"Portfolio delta at {abs(greeks.total_delta)/settings.max_portfolio_delta*100:.0f}% of limit")

        # Notional > $5000 escalation check
        for p in positions:
            if abs(p.market_value) > 5000:
                warnings.append(f"[ESCALATE] {p.symbol} notional ${abs(p.market_value):.0f} > $5000 — requires Steve approval")

        return RiskStatus(
            daily_pnl=round(day_pnl, 2),
            daily_limit=daily_limit,
            daily_pnl_pct=round(abs(day_pnl) / daily_limit * 100, 1) if daily_limit else 0,
            position_count=len(positions),
            max_positions=settings.max_position_count,
            max_single_size=settings.max_single_position_size,
            portfolio_delta=round(greeks.total_delta, 2),
            max_delta=settings.max_portfolio_delta,
            portfolio_greeks=greeks,
            breaches=breaches,
            warnings=warnings,
        )

    async def evaluate_entry(
        self,
        notional: float,
        delta_impact: float,
    ) -> dict:
        """Evaluate whether a new position meets entry criteria."""
        status = await self.get_risk_status()
        issues = []

        if status.breaches:
            issues.append("Existing risk breaches — no new entries")

        if status.position_count >= status.max_positions:
            issues.append(f"At max position count ({status.max_positions})")

        if notional > settings.max_single_position_size:
            issues.append(f"Notional ${notional:.0f} exceeds max ${settings.max_single_position_size:.0f}")

        if abs(status.portfolio_delta + delta_impact) > settings.max_portfolio_delta:
            issues.append(f"Would push delta to {status.portfolio_delta + delta_impact:.1f}")

        # Risk per trade check
        balance = await account_service.get_account_balance()
        account_value = balance.get("liquidation_value", 100000)
        risk_pct = notional / account_value * 100
        if risk_pct > settings.max_risk_per_trade_pct:
            issues.append(f"Risk {risk_pct:.1f}% exceeds max {settings.max_risk_per_trade_pct}%")

        if notional > 5000:
            issues.append("[ESCALATE] Notional > $5000 — requires Steve approval")

        return {
            "approved": len(issues) == 0 or (len(issues) == 1 and "[ESCALATE]" in issues[0]),
            "issues": issues,
            "risk_pct": round(risk_pct, 2),
            "delta_after": round(status.portfolio_delta + delta_impact, 2),
        }


risk_engine = RiskEngine()
