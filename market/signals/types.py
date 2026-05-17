from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class Signal:
    timestamp: datetime  # timezone-aware, US/Central throughout
    source: str          # indicator name that produced this
    confidence: float    # 0.0 to 1.0
    reason: str          # one-line human-readable explanation


@dataclass(frozen=True)
class Bias(Signal):
    direction: Literal["bullish", "bearish", "neutral"] = "neutral"


@dataclass(frozen=True)
class Regime(Signal):
    state: Literal["trending", "ranging", "volatile", "compressed"] = "ranging"


@dataclass(frozen=True)
class Level(Signal):
    price: float = 0.0
    level_type: Literal["support", "resistance", "target", "stop"] = "support"


@dataclass(frozen=True)
class Alert(Signal):
    severity: Literal["info", "warn", "critical"] = "info"
    message: str = ""


@dataclass(frozen=True)
class Action(Signal):
    # Actions are recommendations, not executions. Steve confirms before
    # anything touches the Schwab API. The gate key boundary is never bypassed.
    verb: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceRequest(Signal):
    # Escape hatch for patterns not yet codeable deterministically.
    # FootprintSnapshot (mentioned in spec examples) is illustrative —
    # no such type is defined here. When that indicator is built, its
    # context type will be defined in that task.
    context: Any = None
    question: str = ""
    output_type: str = ""  # name of the expected Signal subclass
