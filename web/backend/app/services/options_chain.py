"""Options chain service — fetches and transforms chain data."""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Optional

import redis.asyncio as redis

from app.config import settings
from app.models.schemas import OptionQuote, OptionsChainRow, OptionType
from app.services.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)


def _generate_demo_chain(
    center_strike: float = 5850,
    num_strikes: int = 25,
    strike_interval: float = 5,
    expiration: date | None = None,
) -> list[OptionsChainRow]:
    """Generate realistic demo options chain data."""
    if expiration is None:
        expiration = date.today()

    rows = []
    dte = max((expiration - date.today()).days, 0)
    time_factor = math.sqrt(max(dte, 0.1) / 365)

    for i in range(-num_strikes, num_strikes + 1):
        strike = center_strike + i * strike_interval
        moneyness = (center_strike - strike) / center_strike

        # Black-Scholes-ish approximation for demo
        iv = 0.16 + abs(moneyness) * 0.8  # Smile
        call_price = max(0.05, center_strike * iv * time_factor * math.exp(-moneyness * 3))
        put_price = max(0.05, center_strike * iv * time_factor * math.exp(moneyness * 3))

        call_delta = max(0.01, min(0.99, 0.5 + moneyness * 5))
        put_delta = call_delta - 1.0
        gamma = max(0, 0.03 * math.exp(-moneyness**2 * 50))
        theta = -iv * center_strike / (365 * 2) * gamma * 100

        call = OptionQuote(
            symbol=f"SPXW {expiration.strftime('%y%m%d')}C{int(strike*1000):08d}",
            strike=strike,
            expiration=expiration,
            option_type=OptionType.CALL,
            bid=round(call_price * 0.95, 2),
            ask=round(call_price * 1.05, 2),
            last=round(call_price, 2),
            volume=int(max(10, 5000 * math.exp(-moneyness**2 * 20))),
            open_interest=int(max(50, 20000 * math.exp(-moneyness**2 * 10))),
            delta=round(call_delta, 4),
            gamma=round(gamma, 4),
            theta=round(theta, 2),
            vega=round(gamma * center_strike * time_factor / 100, 4),
            iv=round(iv, 4),
            in_the_money=strike < center_strike,
        )

        put = OptionQuote(
            symbol=f"SPXW {expiration.strftime('%y%m%d')}P{int(strike*1000):08d}",
            strike=strike,
            expiration=expiration,
            option_type=OptionType.PUT,
            bid=round(put_price * 0.95, 2),
            ask=round(put_price * 1.05, 2),
            last=round(put_price, 2),
            volume=int(max(10, 4000 * math.exp(-moneyness**2 * 20))),
            open_interest=int(max(50, 18000 * math.exp(-moneyness**2 * 10))),
            delta=round(put_delta, 4),
            gamma=round(gamma, 4),
            theta=round(theta, 2),
            vega=round(gamma * center_strike * time_factor / 100, 4),
            iv=round(iv, 4),
            in_the_money=strike > center_strike,
        )

        rows.append(OptionsChainRow(strike=strike, call=call, put=put))

    return rows


class OptionsChainService:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def connect_redis(self):
        try:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            self._redis = None

    async def get_chain(
        self,
        symbol: str = "$SPX",
        expiration: date | None = None,
        strike_count: int = 25,
    ) -> list[OptionsChainRow]:
        """Fetch options chain from Schwab or return demo data."""
        cache_key = f"chain:{symbol}:{expiration}:{strike_count}"

        if self._redis:
            cached = await self._redis.get(cache_key)
            if cached:
                import json
                return [OptionsChainRow.model_validate(r) for r in json.loads(cached)]

        client = get_schwab_client()
        if client is None:
            return _generate_demo_chain(
                num_strikes=strike_count,
                expiration=expiration or date.today(),
            )

        try:
            kwargs = {"symbol": symbol, "strike_count": strike_count}
            if expiration:
                kwargs["from_date"] = expiration
                kwargs["to_date"] = expiration

            resp = client.get_option_chain(**kwargs)
            if resp.status_code == 200:
                chain = self._parse_chain(resp.json())
                if self._redis:
                    import json
                    await self._redis.set(
                        cache_key,
                        json.dumps([r.model_dump(mode="json") for r in chain]),
                        ex=3,
                    )
                return chain
        except Exception as e:
            logger.error(f"Failed to fetch chain: {e}")

        return _generate_demo_chain(num_strikes=strike_count, expiration=expiration)

    async def get_expirations(self, symbol: str = "$SPX") -> list[date]:
        """Get available expirations."""
        client = get_schwab_client()
        if client is None:
            today = date.today()
            # Demo: daily expirations for next 7 days, then weekly
            expirations = []
            for i in range(7):
                from datetime import timedelta
                d = today + timedelta(days=i)
                if d.weekday() < 5:
                    expirations.append(d)
            for w in range(1, 8):
                d = today + timedelta(weeks=w)
                # Friday
                d = d - timedelta(days=(d.weekday() - 4) % 7)
                if d not in expirations:
                    expirations.append(d)
            return sorted(expirations)

        try:
            resp = client.get_option_expiration_chain(symbol)
            if resp.status_code == 200:
                data = resp.json()
                return [
                    date.fromisoformat(exp["expirationDate"])
                    for exp in data.get("expirationList", [])
                ]
        except Exception as e:
            logger.error(f"Failed to fetch expirations: {e}")

        return [date.today()]

    def _parse_chain(self, data: dict) -> list[OptionsChainRow]:
        """Parse Schwab options chain response into our model."""
        rows: dict[float, OptionsChainRow] = {}

        for date_key, strikes in data.get("callExpDateMap", {}).items():
            exp_str = date_key.split(":")[0]
            exp = date.fromisoformat(exp_str)
            for strike_str, options in strikes.items():
                strike = float(strike_str)
                opt = options[0] if options else {}
                quote = self._parse_option(opt, strike, exp, OptionType.CALL)
                if strike not in rows:
                    rows[strike] = OptionsChainRow(strike=strike)
                rows[strike].call = quote

        for date_key, strikes in data.get("putExpDateMap", {}).items():
            exp_str = date_key.split(":")[0]
            exp = date.fromisoformat(exp_str)
            for strike_str, options in strikes.items():
                strike = float(strike_str)
                opt = options[0] if options else {}
                quote = self._parse_option(opt, strike, exp, OptionType.PUT)
                if strike not in rows:
                    rows[strike] = OptionsChainRow(strike=strike)
                rows[strike].put = quote

        return sorted(rows.values(), key=lambda r: r.strike)

    def _parse_option(
        self, opt: dict, strike: float, exp: date, opt_type: OptionType
    ) -> OptionQuote:
        return OptionQuote(
            symbol=opt.get("symbol", ""),
            strike=strike,
            expiration=exp,
            option_type=opt_type,
            bid=opt.get("bid", 0),
            ask=opt.get("ask", 0),
            last=opt.get("last", 0),
            volume=opt.get("totalVolume", 0),
            open_interest=opt.get("openInterest", 0),
            delta=opt.get("delta", 0),
            gamma=opt.get("gamma", 0),
            theta=opt.get("theta", 0),
            vega=opt.get("vega", 0),
            iv=opt.get("volatility", 0) / 100 if opt.get("volatility") else 0,
            in_the_money=opt.get("inTheMoney", False),
        )


options_chain_service = OptionsChainService()
