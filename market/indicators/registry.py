from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable

from market.signals.types import Signal

logger = logging.getLogger(__name__)


@dataclass
class IndicatorDef:
    name: str
    inputs: list[str]   # type names consumed — for future dependency resolver
    output: str         # type name produced — for future dependency resolver
    fn: Callable


# Ordered list. Indicators run in registration order for the POC.
# inputs/output metadata is captured now; topological sort is deferred.
_REGISTRY: list[IndicatorDef] = []


def indicator(inputs: list[str], output: str, name: str):
    """Register an indicator function. Decorator factory."""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY.append(IndicatorDef(name=name, inputs=inputs, output=output, fn=fn))
        return fn
    return decorator


def run_indicators(chain: Any, session: Any, **extra_inputs: Any) -> list[Signal]:
    """Run all registered indicators in registration order."""
    signals: list[Signal] = []
    for defn in _REGISTRY:
        try:
            result = defn.fn(chain, session)
            if result is not None:
                signals.append(result)
        except Exception as exc:
            logger.warning("indicator %s failed: %s", defn.name, exc)
    return signals
