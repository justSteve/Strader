"""Account and position service."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from app.models.schemas import (
    Position,
    PortfolioGreeks,
    OptionType,
)
from app.services.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

# Demo positions for when API is unavailable
DEMO_POSITIONS = [
    Position(
        symbol="SPXW 260309C05850000",
        description="SPX Mar 09 5850 Call (butterfly center)",
        quantity=-2,
        average_price=18.50,
        market_value=-3540.00,
        day_pnl=120.00,
        total_pnl=160.00,
        pnl_pct=4.32,
        delta=-0.48,
        gamma=-0.032,
        theta=12.40,
        vega=-0.15,
        option_type=OptionType.CALL,
        strike=5850.0,
        expiration=date.today(),
    ),
    Position(
        symbol="SPXW 260309C05840000",
        description="SPX Mar 09 5840 Call (butterfly wing)",
        quantity=1,
        average_price=24.20,
        market_value=2380.00,
        day_pnl=-45.00,
        total_pnl=-40.00,
        pnl_pct=-1.65,
        delta=0.62,
        gamma=0.028,
        theta=-8.60,
        vega=0.12,
        option_type=OptionType.CALL,
        strike=5840.0,
        expiration=date.today(),
    ),
    Position(
        symbol="SPXW 260309C05860000",
        description="SPX Mar 09 5860 Call (butterfly wing)",
        quantity=1,
        average_price=13.80,
        market_value=1420.00,
        day_pnl=-30.00,
        total_pnl=40.00,
        pnl_pct=2.90,
        delta=0.35,
        gamma=0.026,
        theta=-7.80,
        vega=0.11,
        option_type=OptionType.CALL,
        strike=5860.0,
        expiration=date.today(),
    ),
    Position(
        symbol="SPXW 260310P05800000",
        description="SPX Mar 10 5800 Put (long)",
        quantity=2,
        average_price=8.40,
        market_value=1520.00,
        day_pnl=-180.00,
        total_pnl=-160.00,
        pnl_pct=-9.52,
        delta=-0.22,
        gamma=0.015,
        theta=-4.20,
        vega=0.09,
        option_type=OptionType.PUT,
        strike=5800.0,
        expiration=date(2026, 3, 10),
    ),
]


class AccountService:
    def __init__(self):
        self._account_hash: Optional[str] = None

    async def _get_account_hash(self) -> Optional[str]:
        if self._account_hash:
            return self._account_hash

        client = get_schwab_client()
        if client is None:
            return None

        try:
            resp = client.get_account_numbers()
            if resp.status_code == 200:
                accounts = resp.json()
                if accounts:
                    self._account_hash = accounts[0].get("hashValue")
                    return self._account_hash
        except Exception as e:
            logger.error(f"Failed to get account hash: {e}")

        return None

    async def get_positions(self) -> list[Position]:
        """Get current positions from Schwab or demo data."""
        client = get_schwab_client()
        if client is None:
            return DEMO_POSITIONS

        account_hash = await self._get_account_hash()
        if account_hash is None:
            return DEMO_POSITIONS

        try:
            resp = client.get_account(account_hash, fields=["positions"])
            if resp.status_code == 200:
                data = resp.json()
                return self._parse_positions(data)
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")

        return DEMO_POSITIONS

    async def get_portfolio_greeks(self) -> PortfolioGreeks:
        """Calculate aggregate portfolio Greeks."""
        positions = await self.get_positions()
        greeks = PortfolioGreeks()

        for pos in positions:
            qty = pos.quantity
            greeks.total_delta += pos.delta * qty * 100
            greeks.total_gamma += pos.gamma * qty * 100
            greeks.total_theta += pos.theta * qty
            greeks.total_vega += pos.vega * qty * 100
            greeks.net_premium += pos.market_value

        greeks.total_delta = round(greeks.total_delta, 2)
        greeks.total_gamma = round(greeks.total_gamma, 4)
        greeks.total_theta = round(greeks.total_theta, 2)
        greeks.total_vega = round(greeks.total_vega, 4)
        greeks.net_premium = round(greeks.net_premium, 2)

        return greeks

    async def get_account_balance(self) -> dict:
        """Get account balance summary."""
        client = get_schwab_client()
        if client is None:
            return {
                "liquidation_value": 125000.00,
                "buying_power": 98000.00,
                "cash_balance": 45000.00,
                "day_pnl": -135.00,
            }

        account_hash = await self._get_account_hash()
        if account_hash is None:
            return {}

        try:
            resp = client.get_account(account_hash)
            if resp.status_code == 200:
                data = resp.json()
                bal = data.get("securitiesAccount", {}).get("currentBalances", {})
                return {
                    "liquidation_value": bal.get("liquidationValue", 0),
                    "buying_power": bal.get("buyingPower", 0),
                    "cash_balance": bal.get("cashBalance", 0),
                    "day_pnl": bal.get("dayTradingBuyingPower", 0),
                }
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")

        return {}

    def _parse_positions(self, data: dict) -> list[Position]:
        """Parse Schwab account positions response."""
        positions = []
        account = data.get("securitiesAccount", {})

        for pos_data in account.get("positions", []):
            inst = pos_data.get("instrument", {})
            symbol = inst.get("symbol", "")
            quantity = int(pos_data.get("longQuantity", 0) - pos_data.get("shortQuantity", 0))
            avg_price = pos_data.get("averagePrice", 0)
            market_value = pos_data.get("marketValue", 0)
            day_pnl = pos_data.get("currentDayProfitLoss", 0)

            cost = avg_price * abs(quantity) * 100
            total_pnl = market_value - cost if quantity > 0 else cost - abs(market_value)
            pnl_pct = (total_pnl / abs(cost) * 100) if cost else 0

            positions.append(Position(
                symbol=symbol,
                description=inst.get("description", symbol),
                quantity=quantity,
                average_price=avg_price,
                market_value=market_value,
                day_pnl=day_pnl,
                total_pnl=round(total_pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                option_type=OptionType(inst["putCall"]) if "putCall" in inst else None,
                strike=inst.get("strikePrice"),
                expiration=date.fromisoformat(inst["expirationDate"][:10]) if "expirationDate" in inst else None,
            ))

        return positions


account_service = AccountService()
