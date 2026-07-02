"""Strader — the strategy layer over Strader's carried datafeed infra.

Scope (per COO plans 2026-06-29-strader2-greenfield-plan.md, co-r10h / st-dp3;
folded in per 2026-07-02-strader2-fold-in-plan.md, co-wu3n):
  - Carries the proven datafeed infrastructure by *import* (see strader.feeds),
    never by copy — the feed stays single-source.
  - Focus strategy: the 0DTE long single as a futures proxy, triggered by
    Carmine setups recognized from the datafeed, with Mancini levels as the
    reference frame. Butterflies stay as manual/reference only.

This package stays intentionally small and clean. It was built as the
quarantined ``strader2`` package while the parent tree was cleaned, then folded
in as the canonical ``strader`` package on 2026-07-02 (co-wu3n) once that
cleanup had landed.
"""

__all__ = ["config", "feeds"]
