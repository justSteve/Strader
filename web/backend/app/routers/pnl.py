"""P&L chart data endpoints."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.models.schemas import DailyPnL

router = APIRouter(prefix="/pnl", tags=["pnl"])


def _generate_demo_daily_pnl(days: int = 30) -> list[DailyPnL]:
    """Generate demo daily P&L history."""
    results = []
    today = date.today()
    cumulative = 0

    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue

        trades = random.randint(2, 8)
        wins = random.randint(1, trades)
        losses = trades - wins

        realized = round(random.gauss(150, 400), 2)
        unrealized = round(random.gauss(0, 200), 2)
        total = realized + unrealized
        cumulative += total
        drawdown = round(min(0, total - abs(total * 0.3)), 2)

        results.append(DailyPnL(
            trade_date=d,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=round(total, 2),
            trade_count=trades,
            win_count=wins,
            loss_count=losses,
            max_drawdown=drawdown,
        ))

    return results


def _generate_demo_intraday() -> list[dict]:
    """Generate demo intraday P&L curve."""
    points = []
    pnl = 0

    for minute in range(0, 390, 1):  # 9:30 to 16:00
        hour = 9 + (minute + 30) // 60
        mins = (minute + 30) % 60
        t = f"{hour:02d}:{mins:02d}"

        pnl += random.gauss(0.5, 15)
        points.append({"time": t, "pnl": round(pnl, 2)})

    return points


@router.get("/daily")
async def get_daily_pnl(days: int = Query(30, ge=1, le=365)):
    return _generate_demo_daily_pnl(days)


@router.get("/intraday")
async def get_intraday_pnl():
    return _generate_demo_intraday()
