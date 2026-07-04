"""Orderflow layer — deterministic computation over the DataBento ES stream.

Design of record: docs/superpowers/specs/2026-07-03-orderflow-signal-layer-design.md
(st-l5o). Modules arrive bead-by-bead:

  bars.py    — volume-bar / footprint builder (st-uqf)
  replay.py  — corpus-day reader: the canonical sort + dedup rule (st-uqf)

The hard constraint everywhere: replaying the same recorded stream produces
byte-identical output. Order only by (ts_event, sequence); no wall-clock.
"""
from market.orderflow.bars import build_bars
from market.orderflow.replay import read_corpus_day

__all__ = ["build_bars", "read_corpus_day"]
