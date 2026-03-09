"""Options chain endpoints."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.options_chain import options_chain_service

router = APIRouter(prefix="/options", tags=["options"])


@router.get("/chain")
async def get_options_chain(
    symbol: str = Query("$SPX"),
    expiration: Optional[date] = Query(None),
    strike_count: int = Query(25, ge=5, le=50),
):
    return await options_chain_service.get_chain(symbol, expiration, strike_count)


@router.get("/expirations")
async def get_expirations(symbol: str = Query("$SPX")):
    return await options_chain_service.get_expirations(symbol)
