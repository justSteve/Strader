"""Strader2 — the greenfield strategy layer over Strader's carried datafeed infra.

Scope (per COO plan 2026-06-29-strader2-greenfield-plan.md, co-r10h / st-dp3):
  - Carries the proven datafeed infrastructure by *import* (see strader2.feeds),
    never by copy — the feed stays single-source.
  - Focus strategy: the 0DTE long single as a futures proxy, triggered by
    Carmine setups recognized from the datafeed, with Mancini levels as the
    reference frame. Butterflies stay as manual/reference only.

This package is intentionally small and clean; the ~80 files of factory/GC
scaffolding in the parent tree are left untouched and out of scope.
"""

__all__ = ["config", "feeds"]
