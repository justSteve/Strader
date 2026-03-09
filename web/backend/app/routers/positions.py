"""Position dashboard endpoints."""

from fastapi import APIRouter

from app.services.positions import position_service

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
async def get_positions():
    return await position_service.get_positions()


@router.get("/summary")
async def get_portfolio_summary():
    return await position_service.get_portfolio_summary()


@router.get("/pnl/history")
async def get_pnl_history(days: int = 30):
    return await position_service.get_pnl_history(days)


@router.get("/pnl/intraday")
async def get_intraday_pnl():
    return await position_service.get_intraday_pnl()


@router.get("/{position_id}")
async def get_position(position_id: int):
    pos = await position_service.get_position(position_id)
    if not pos:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Position not found")
    return pos
