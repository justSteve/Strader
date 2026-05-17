from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from market.entities.instrument import Contract


@dataclass(frozen=True)
class ButterflyTemplate:
    center: str                           # "ATM", "ATM+5", "ATM-5", or absolute strike as string
    width: int                            # distance in points between legs
    expiry: str                           # "0DTE", "1DTE", or ISO date string
    contract_type: Literal["CALL", "PUT"]


@dataclass(frozen=True)
class ButterflyInstance:
    template: ButterflyTemplate
    lower: Contract
    center: Contract    # held at 2x quantity
    upper: Contract
    net_debit: float    # cost to enter (positive = debit paid)
    max_profit: float   # at expiry if pinned at center strike
    max_loss: float     # equals net_debit
    breakeven_lower: float
    breakeven_upper: float
