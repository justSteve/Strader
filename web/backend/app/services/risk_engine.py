"""Risk engine — monitors portfolio against risk limits, generates alerts."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.services.positions import position_service

logger = logging.getLogger(__name__)


class Alert:
    def __init__(self, level: str, category: str, message: str, value: float, limit: float):
        self.level = level  # WARNING, BREACH
        self.category = category
        self.message = message
        self.value = value
        self.limit = limit
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "value": self.value,
            "limit": self.limit,
            "timestamp": self.timestamp.isoformat(),
        }


class RiskEngine:
    """Monitors portfolio risk limits and generates breach alerts."""

    def __init__(self) -> None:
        self._alerts: list[Alert] = []

    async def check_risk(self) -> dict[str, Any]:
        """Run all risk checks and return current risk status."""
        summary = await position_service.get_portfolio_summary()
        self._alerts = []

        checks = {
            "daily_loss": self._check_daily_loss(summary),
            "position_count": self._check_position_count(summary),
            "portfolio_delta": self._check_portfolio_delta(summary),
            "position_sizes": await self._check_position_sizes(),
        }

        return {
            "status": "BREACH" if any(c["breached"] for c in checks.values()) else "OK",
            "checks": checks,
            "alerts": [a.to_dict() for a in self._alerts],
            "summary": summary,
            "limits": {
                "max_daily_loss": settings.max_daily_loss,
                "max_position_count": settings.max_position_count,
                "max_portfolio_delta": settings.max_portfolio_delta,
                "max_single_position_notional": settings.max_single_position_notional,
                "risk_per_trade_pct": settings.risk_per_trade_pct,
            },
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def _check_daily_loss(self, summary: dict) -> dict[str, Any]:
        day_pnl = summary["day_pnl"]
        limit = settings.max_daily_loss
        breached = day_pnl < -limit
        if breached:
            self._alerts.append(
                Alert("BREACH", "daily_loss", f"Daily loss ${abs(day_pnl):.0f} exceeds limit ${limit:.0f}", day_pnl, -limit)
            )
        elif day_pnl < -limit * 0.8:
            self._alerts.append(
                Alert("WARNING", "daily_loss", f"Daily loss approaching limit: ${abs(day_pnl):.0f} / ${limit:.0f}", day_pnl, -limit)
            )
        return {"value": day_pnl, "limit": -limit, "breached": breached, "pct_used": abs(day_pnl) / limit * 100}

    def _check_position_count(self, summary: dict) -> dict[str, Any]:
        count = summary["position_count"]
        limit = settings.max_position_count
        breached = count >= limit
        if breached:
            self._alerts.append(
                Alert("BREACH", "position_count", f"Position count {count} at limit {limit}", count, limit)
            )
        return {"value": count, "limit": limit, "breached": breached, "pct_used": count / limit * 100}

    def _check_portfolio_delta(self, summary: dict) -> dict[str, Any]:
        delta = abs(summary["greeks"]["delta"])
        limit = settings.max_portfolio_delta
        breached = delta > limit
        if breached:
            self._alerts.append(
                Alert("BREACH", "portfolio_delta", f"Portfolio delta {delta:.2f} exceeds limit {limit:.0f}", delta, limit)
            )
        elif delta > limit * 0.8:
            self._alerts.append(
                Alert("WARNING", "portfolio_delta", f"Portfolio delta approaching limit: {delta:.2f} / {limit:.0f}", delta, limit)
            )
        return {"value": delta, "limit": limit, "breached": breached, "pct_used": delta / limit * 100}

    async def _check_position_sizes(self) -> dict[str, Any]:
        positions = await position_service.get_positions()
        limit = settings.max_single_position_notional
        breached = False
        for p in positions:
            if p["market_value"] > limit:
                breached = True
                self._alerts.append(
                    Alert(
                        "BREACH",
                        "position_size",
                        f"{p['symbol']} notional ${p['market_value']:.0f} exceeds ${limit:.0f}",
                        p["market_value"],
                        limit,
                    )
                )
        return {"limit": limit, "breached": breached}

    async def evaluate_entry(
        self,
        strike: float,
        expiration: str,
        direction: str,
        strategy: str,
        quantity: int = 1,
        estimated_cost: float = 0,
    ) -> dict[str, Any]:
        """Evaluate whether a proposed trade meets entry criteria."""
        summary = await position_service.get_portfolio_summary()
        signals: list[dict[str, str]] = []
        can_enter = True

        # Check position count
        if summary["position_count"] >= settings.max_position_count:
            can_enter = False
            signals.append({"signal": "REJECT", "reason": "Position count at limit"})

        # Check daily loss
        if summary["day_pnl"] < -settings.max_daily_loss * 0.8:
            can_enter = False
            signals.append({"signal": "REJECT", "reason": "Approaching daily loss limit"})

        # Check notional
        if estimated_cost > settings.max_single_position_notional:
            can_enter = False
            signals.append({"signal": "REJECT", "reason": f"Notional ${estimated_cost:.0f} exceeds single position limit"})

        if can_enter:
            signals.append({"signal": "PASS", "reason": "All risk checks passed"})

        return {
            "can_enter": can_enter,
            "signals": signals,
            "portfolio_after": {
                "position_count": summary["position_count"] + 1,
                "estimated_delta_impact": 0,  # Would calculate from greeks
            },
        }

    async def get_max_loss_scenarios(self) -> list[dict[str, Any]]:
        """Calculate max loss under various SPX move scenarios."""
        positions = await position_service.get_positions()
        scenarios = []
        for move_pct in [-3.0, -2.0, -1.0, -0.5, 0, 0.5, 1.0, 2.0, 3.0]:
            # Simplified: use delta approximation
            total_pnl = 0.0
            for p in positions:
                # PnL ≈ delta * move_points * quantity * 100
                spot = 5800  # approximate
                move_points = spot * move_pct / 100
                pnl = p["delta"] * move_points * p["quantity"] * 100
                total_pnl += pnl
            scenarios.append(
                {
                    "move_pct": move_pct,
                    "estimated_pnl": round(total_pnl, 2),
                }
            )
        return scenarios


risk_engine = RiskEngine()
