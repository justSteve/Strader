from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class GexProfile:
    """Computed gamma exposure profile for an option chain at a given spot.

    Sign convention (squeezemetrics / spotgamma standard):
      net_gex > 0  → dealers are net long gamma (suppressive regime)
      net_gex < 0  → dealers are net short gamma (amplifying regime)

    Units: $-gamma per 1% spot move, i.e.
      gamma_per_contract * OI * 100 (contract multiplier) * spot²

    `by_strike` maps strike price → net per-strike GEX contribution
    (calls plus puts at that strike). A "gamma wall" appears as a
    large positive entry; a strike where puts dominate appears negative.
    """
    spot: float
    net_gex: float
    net_gex_calls: float
    net_gex_puts: float
    by_strike: dict[float, float]
