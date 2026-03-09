"""Risk panel endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.alerts import alert_service
from app.services.risk_engine import risk_engine

router = APIRouter(prefix="/api/risk", tags=["risk"])


class EntryEvalRequest(BaseModel):
    strike: float
    expiration: str
    direction: str = "LONG"
    strategy: str = "BUTTERFLY"
    quantity: int = 1
    estimated_cost: float = 0


@router.get("/status")
async def get_risk_status():
    return await risk_engine.check_risk()


@router.get("/scenarios")
async def get_max_loss_scenarios():
    return await risk_engine.get_max_loss_scenarios()


@router.post("/evaluate-entry")
async def evaluate_entry(req: EntryEvalRequest):
    return await risk_engine.evaluate_entry(
        strike=req.strike,
        expiration=req.expiration,
        direction=req.direction,
        strategy=req.strategy,
        quantity=req.quantity,
        estimated_cost=req.estimated_cost,
    )


@router.get("/alerts")
async def get_alerts(limit: int = 50):
    return await alert_service.get_alerts(limit)
