"""Position and account API routes."""

from fastapi import APIRouter

from ...services.positions import get_positions, get_portfolio_greeks
from ...schemas.options import PositionResponse, PortfolioGreeks

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("/", response_model=list[PositionResponse])
async def list_positions():
    """Get all open SPX positions."""
    return await get_positions()


@router.get("/greeks", response_model=PortfolioGreeks)
async def portfolio_greeks():
    """Get aggregate portfolio greeks."""
    return await get_portfolio_greeks()
