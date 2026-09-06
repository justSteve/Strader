"""
Boundary layer: raw external data -> typed market entities.

Each module in this package handles one ingest source. Public symbols
are re-exported here so callers can `from market.ingest import X`
regardless of which source X comes from.

`mancini.py` was pruned 2026-09-06 — `session_from_mancini` had no consumer
left anywhere in the tree, the letter parse having moved to `runbook/mancini/`
years of sessions ago. It is in the `pre-prune-2026-09-05` tag if the shape is
ever wanted. `schwab.py` stayed: `chain_from_schwab` is how the LIVE butterfly
resolver's tests build a chain from a fixture. [st-rfjg, audit row 36]

Re-exports are LAZY (PEP 562). `databento.py` imports the `databento` lib at
module level, and until 2026-09-06 this file pulled it in eagerly — so
`import market.ingest.gexbot`, which needs nothing but httpx, was impossible
on any box without the feed lib. That is what had CI red from 2026-09-05
(`tests/scripts/test_gexbot_env_routing.py` collecting through this file).
The names below still resolve identically for callers; they are just resolved
on first access instead of at package import. [st-v55j]
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # import-time only for type checkers, never at runtime
    from market.ingest.databento import (LiveClient, quote_from_databento,
                                         trade_from_databento)
    from market.ingest.schwab import chain_from_schwab

#: Public symbol -> the submodule that defines it.
_SOURCES = {
    "chain_from_schwab": "market.ingest.schwab",
    "LiveClient": "market.ingest.databento",
    "trade_from_databento": "market.ingest.databento",
    "quote_from_databento": "market.ingest.databento",
}

__all__ = list(_SOURCES)


def __getattr__(name: str):
    """Resolve a re-exported symbol on first access.

    A missing feed lib now fails when the symbol that needs it is actually
    used, naming that symbol — not when an unrelated sibling is imported.
    """
    try:
        target = _SOURCES[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    from importlib import import_module
    value = getattr(import_module(target), name)
    globals()[name] = value  # cache: subsequent lookups skip __getattr__
    return value


def __dir__():
    return sorted(set(globals()) | set(_SOURCES))
