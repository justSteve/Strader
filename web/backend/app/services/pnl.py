"""P&L tracking service."""

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session
from ..models.trade import DailyPnL
from ..schemas.options import PnLSummary
from .positions import get_positions

logger = logging.getLogger(__name__)


async def get_daily_pnl(trade_date: date | None = None) -> PnLSummary:
    """Get P&L summary for a given date."""
    target_date = trade_date or date.today()

    async with async_session() as session:
        result = await session.execute(
            select(DailyPnL).where(DailyPnL.trade_date == target_date)
        )
        record = result.scalar_one_or_none()

    if record:
        win_rate = None
        if record.trade_count and record.trade_count > 0:
            win_rate = round(record.win_count / record.trade_count * 100, 1)

        return PnLSummary(
            date=record.trade_date,
            realized_pnl=float(record.realized_pnl),
            unrealized_pnl=float(record.unrealized_pnl),
            total_pnl=float(record.realized_pnl) + float(record.unrealized_pnl),
            fees=float(record.fees),
            trade_count=record.trade_count,
            win_rate=win_rate,
            max_drawdown=float(record.max_drawdown),
        )

    # Calculate from live positions if no DB record
    positions = await get_positions()
    unrealized = sum(p.pnl_total or 0 for p in positions)
    day_pnl = sum(p.pnl_day or 0 for p in positions)

    return PnLSummary(
        date=target_date,
        realized_pnl=0,
        unrealized_pnl=unrealized,
        total_pnl=day_pnl,
        fees=0,
        trade_count=len(positions),
        win_rate=None,
        max_drawdown=min(day_pnl, 0),
    )


async def get_pnl_history(days: int = 30) -> list[PnLSummary]:
    """Get P&L history for the last N days."""
    async with async_session() as session:
        result = await session.execute(
            select(DailyPnL)
            .order_by(DailyPnL.trade_date.desc())
            .limit(days)
        )
        records = result.scalars().all()

    history = []
    for r in records:
        win_rate = None
        if r.trade_count and r.trade_count > 0:
            win_rate = round(r.win_count / r.trade_count * 100, 1)

        history.append(PnLSummary(
            date=r.trade_date,
            realized_pnl=float(r.realized_pnl),
            unrealized_pnl=float(r.unrealized_pnl),
            total_pnl=float(r.realized_pnl) + float(r.unrealized_pnl),
            fees=float(r.fees),
            trade_count=r.trade_count,
            win_rate=win_rate,
            max_drawdown=float(r.max_drawdown),
        ))

    # If no history, return demo data
    if not history:
        return _demo_pnl_history()

    return history


def _demo_pnl_history() -> list[PnLSummary]:
    """Generate demo P&L history."""
    from datetime import timedelta
    import random

    history = []
    today = date.today()
    cumulative = 0

    for i in range(30, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue

        daily = round(random.gauss(50, 300), 2)
        cumulative += daily

        history.append(PnLSummary(
            date=d,
            realized_pnl=daily,
            unrealized_pnl=0,
            total_pnl=daily,
            fees=round(abs(daily) * 0.02, 2),
            trade_count=random.randint(2, 8),
            win_rate=round(random.uniform(40, 70), 1),
            max_drawdown=round(min(daily, 0), 2),
        ))

    return history
