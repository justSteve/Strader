from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal

from market.entities.level import Level


@dataclass(frozen=True)
class Session:
    date: date
    underlying_price: float
    open: float
    high: float
    low: float
    gex_posture: Literal["positive", "negative", "neutral"]
    vix: float
    mancini_supports: tuple[Level, ...]      # tuple not list: frozen dataclass requires hashable fields
    mancini_resistances: tuple[Level, ...]
