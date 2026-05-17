from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal

from market.entities.instrument import Contract


def strike_key(price: float) -> int:
    """Convert strike price to collision-safe int key. 5800.5 -> 58005."""
    return round(price * 10)


@dataclass(frozen=True)
class Chain:
    underlying: str
    expiry: date
    calls: dict[int, Contract]   # strike_key(strike) -> Contract
    puts: dict[int, Contract]
    underlying_price: float

    def call(self, strike: float) -> Contract:
        return self.calls[strike_key(strike)]

    def put(self, strike: float) -> Contract:
        return self.puts[strike_key(strike)]

    def nearest_call(self, price: float) -> Contract:
        key = min(self.calls.keys(), key=lambda k: abs(k - strike_key(price)))
        return self.calls[key]

    def nearest_put(self, price: float) -> Contract:
        key = min(self.puts.keys(), key=lambda k: abs(k - strike_key(price)))
        return self.puts[key]

    def range(self, low: float, high: float, side: Literal["CALL", "PUT"]) -> list[Contract]:
        source = self.calls if side == "CALL" else self.puts
        lo, hi = strike_key(low), strike_key(high)
        return [c for k, c in sorted(source.items()) if lo <= k <= hi]
