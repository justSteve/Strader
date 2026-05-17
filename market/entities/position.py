from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from market.entities.spread import ButterflyInstance


@dataclass(frozen=True)
class Position:
    spread: ButterflyInstance
    entry_price: float
    quantity: int
    entry_time: datetime    # timezone-aware, US/Central
    current_value: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_value - self.entry_price) * self.quantity * 100
