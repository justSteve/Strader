from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Level:
    price: float
    label: Literal["support", "resistance", "target", "stop"]
    source: str           # "mancini", "manual", "luxalgo"
    annotation: str = ""  # "major", "minor", or empty
