"""
Boundary layer: raw external data -> typed market entities.

Each module in this package handles one ingest source. Public symbols
are re-exported here so callers can `from market.ingest import X`
regardless of which source X comes from.
"""
from market.ingest.schwab import chain_from_schwab
from market.ingest.mancini import session_from_mancini
from market.ingest.databento import LiveClient, quote_from_databento, trade_from_databento

__all__ = [
    "chain_from_schwab",
    "session_from_mancini",
    "LiveClient",
    "trade_from_databento",
    "quote_from_databento",
]
