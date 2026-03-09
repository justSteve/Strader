"""Position and account service — tracks open positions with live PnL and greeks."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# In-memory position store (production: PostgreSQL via SQLAlchemy)
_demo_positions: list[dict[str, Any]] = [
    {
        "id": 1,
        "symbol": "SPX 250310C5800",
        "underlying": "SPX",
        "instrument_type": "OPTION",
        "put_call": "CALL",
        "strike": 5800,
        "expiration": "2025-03-10T20:00:00Z",
        "quantity": 2,
        "average_price": 12.50,
        "market_value": 2800.0,
        "cost_basis": 2500.0,
        "unrealized_pnl": 300.0,
        "day_pnl": 150.0,
        "delta": 0.52,
        "gamma": 0.0045,
        "theta": -2.35,
        "vega": 0.18,
        "strategy": "SINGLE",
    },
    {
        "id": 2,
        "symbol": "SPX 250310 BFLY 5790/5800/5810",
        "underlying": "SPX",
        "instrument_type": "OPTION",
        "put_call": "CALL",
        "strike": 5800,
        "expiration": "2025-03-10T20:00:00Z",
        "quantity": 5,
        "average_price": 1.80,
        "market_value": 1100.0,
        "cost_basis": 900.0,
        "unrealized_pnl": 200.0,
        "day_pnl": 75.0,
        "delta": 0.05,
        "gamma": 0.012,
        "theta": -0.85,
        "vega": 0.02,
        "strategy": "BUTTERFLY",
    },
    {
        "id": 3,
        "symbol": "SPX 250310P5750",
        "underlying": "SPX",
        "instrument_type": "OPTION",
        "put_call": "PUT",
        "strike": 5750,
        "expiration": "2025-03-10T20:00:00Z",
        "quantity": 1,
        "average_price": 3.20,
        "market_value": 280.0,
        "cost_basis": 320.0,
        "unrealized_pnl": -40.0,
        "day_pnl": -20.0,
        "delta": -0.15,
        "gamma": 0.003,
        "theta": -1.10,
        "vega": 0.08,
        "strategy": "SINGLE",
    },
]


class PositionService:
    """Manages positions: retrieval, live greeks rollup, PnL tracking."""

    def __init__(self) -> None:
        self._positions = list(_demo_positions)

    async def get_positions(self) -> list[dict[str, Any]]:
        return self._positions

    async def get_position(self, position_id: int) -> Optional[dict[str, Any]]:
        for p in self._positions:
            if p["id"] == position_id:
                return p
        return None

    async def get_portfolio_summary(self) -> dict[str, Any]:
        """Aggregate portfolio greeks and PnL."""
        total_delta = sum(p["delta"] * p["quantity"] for p in self._positions)
        total_gamma = sum(p["gamma"] * p["quantity"] for p in self._positions)
        total_theta = sum(p["theta"] * p["quantity"] for p in self._positions)
        total_vega = sum(p["vega"] * p["quantity"] for p in self._positions)
        total_unrealized = sum(p["unrealized_pnl"] for p in self._positions)
        total_day_pnl = sum(p["day_pnl"] for p in self._positions)
        total_market_value = sum(p["market_value"] for p in self._positions)
        total_cost = sum(p["cost_basis"] for p in self._positions)

        return {
            "position_count": len(self._positions),
            "total_market_value": round(total_market_value, 2),
            "total_cost_basis": round(total_cost, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "day_pnl": round(total_day_pnl, 2),
            "greeks": {
                "delta": round(total_delta, 4),
                "gamma": round(total_gamma, 6),
                "theta": round(total_theta, 4),
                "vega": round(total_vega, 4),
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_pnl_history(self, days: int = 30) -> list[dict[str, Any]]:
        """Return daily PnL history (demo data)."""
        import numpy as np

        history = []
        cumulative = 0.0
        now = datetime.now(timezone.utc)
        for i in range(days, 0, -1):
            daily = float(np.random.normal(50, 200))
            cumulative += daily
            history.append(
                {
                    "date": (
                        now.replace(hour=0, minute=0, second=0, microsecond=0)
                        - __import__("datetime").timedelta(days=i)
                    ).isoformat(),
                    "daily_pnl": round(daily, 2),
                    "cumulative_pnl": round(cumulative, 2),
                    "trade_count": max(0, int(np.random.poisson(3))),
                }
            )
        return history

    async def get_intraday_pnl(self) -> list[dict[str, Any]]:
        """Return intraday PnL curve (demo: 1-minute intervals from open)."""
        import numpy as np

        data = []
        pnl = 0.0
        for minute in range(390):  # 6.5 hours of trading
            pnl += float(np.random.normal(0.5, 15))
            hour = 9 + (minute + 30) // 60
            min_of_hour = (minute + 30) % 60
            data.append(
                {
                    "time": f"{hour:02d}:{min_of_hour:02d}",
                    "pnl": round(pnl, 2),
                    "minute": minute,
                }
            )
        return data


position_service = PositionService()
