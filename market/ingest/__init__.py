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
"""
from market.ingest.schwab import chain_from_schwab
from market.ingest.databento import LiveClient, quote_from_databento, trade_from_databento

__all__ = [
    "chain_from_schwab",
    "LiveClient",
    "trade_from_databento",
    "quote_from_databento",
]
