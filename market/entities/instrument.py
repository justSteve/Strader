from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class Instrument:
    symbol: str
    underlying: str


@dataclass(frozen=True)
class Index(Instrument):
    pass


@dataclass(frozen=True)
class Contract(Instrument):
    strike: float
    expiry: date
    contract_type: Literal["CALL", "PUT"]
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2
