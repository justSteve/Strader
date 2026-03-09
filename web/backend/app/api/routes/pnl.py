"""P&L API routes."""

from datetime import date

from fastapi import APIRouter, Query

from ...services.pnl import get_daily_pnl, get_pnl_history
from ...schemas.options import PnLSummary

router = APIRouter(prefix="/api/pnl", tags=["pnl"])


@router.get("/today", response_model=PnLSummary)
async def today_pnl():
    """Get today's P&L summary."""
    return await get_daily_pnl()


@router.get("/history", response_model=list[PnLSummary])
async def pnl_history(days: int = Query(30, ge=1, le=365)):
    """Get P&L history."""
    return await get_pnl_history(days)
