"""Risk monitoring endpoints."""
from fastapi import APIRouter

from app.services.risk_engine import risk_engine

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/status")
async def get_risk_status():
    return await risk_engine.get_risk_status()


@router.post("/evaluate")
async def evaluate_entry(notional: float, delta_impact: float = 0):
    return await risk_engine.evaluate_entry(notional, delta_impact)
