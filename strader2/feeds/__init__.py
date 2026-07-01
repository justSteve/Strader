"""strader2.feeds — the single seam over the carried datafeed infrastructure.

Strader2 does NOT copy or move the proven datafeed code (`market.ingest`,
`market.corpus`, `broker_schwab`, `runbook.mancini`). It imports it. This module
is the one documented place that re-exports the carried entry points, so the
rest of strader2 depends on ``strader2.feeds.<x>()`` rather than reaching into
``market.*`` directly. If the carried layout ever moves, only this file changes.

Accessors are **lazy** — the heavy optional deps (databento, schwab) are imported
only when a feed is actually requested, so ``import strader2.feeds`` stays cheap
and side-effect free.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

# name -> dotted module path in the carried infra. The catalog doubles as
# documentation of exactly what Strader2 carries.
CARRIED: dict[str, str] = {
    # market data ingest (raw API -> typed entities, US/Central normalized)
    "ingest_databento": "market.ingest.databento",
    "ingest_schwab": "market.ingest.schwab",
    "ingest_mancini": "market.ingest.mancini",
    "ingest_gexbot": "market.ingest.gexbot",
    # append-only corpus (history-is-the-value)
    "corpus_paths": "market.corpus.paths",
    "corpus_writer": "market.corpus.writer",
    "corpus_schwab_stream": "market.corpus.schwab_stream",
    "corpus_gexbot_stream": "market.corpus.gexbot_stream",
    # broker access behind the ~/.schwab_gate_key hard gate
    "broker_client": "broker_schwab.client",
    # Mancini reference layer — canonical ParseResult schema + bounded-LLM parser
    "mancini_schema": "runbook.mancini.schema",
    "mancini_parse": "runbook.mancini.parse",
}


def carried(name: str) -> Any:
    """Lazily import and return a carried infra module by its short name."""
    try:
        dotted = CARRIED[name]
    except KeyError:
        raise KeyError(
            f"unknown carried feed {name!r}; known: {sorted(CARRIED)}"
        ) from None
    return import_module(dotted)


def available() -> dict[str, bool]:
    """Report which carried modules import cleanly in this environment.

    Used by the Phase-1 smoke test. A module can be *catalogued* but not
    *importable* if its optional dep (e.g. databento) isn't installed — that is
    information, not an error, so this returns a map rather than raising.
    """
    status: dict[str, bool] = {}
    for name, dotted in CARRIED.items():
        try:
            import_module(dotted)
            status[name] = True
        except Exception:
            status[name] = False
    return status
