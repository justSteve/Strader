"""Position and account endpoints."""
from fastapi import APIRouter

from app.services.account import account_service

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/")
async def get_positions():
    return await account_service.get_positions()


@router.get("/greeks")
async def get_portfolio_greeks():
    return await account_service.get_portfolio_greeks()


@router.get("/balance")
async def get_account_balance():
    return await account_service.get_account_balance()
