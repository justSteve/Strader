"""
Numeric GEX calculator.

Operates on a fully-populated Chain (gamma + open_interest per Contract)
and emits a GexProfile. Companion to `gex.py`, which is the regime
classifier that interprets a (posture, vix) pair — this module *produces*
the numeric posture inputs.

V1 uses chain-supplied gamma (e.g. Schwab's published values). A V2
revision will recompute gamma via Black-Scholes from chain-implied vol
so we control the model assumptions end-to-end.
"""
from __future__ import annotations

from market.entities.chain import Chain
from market.entities.gex_profile import GexProfile

CONTRACT_MULTIPLIER = 100  # standard equity option contract size


def compute_gex(chain: Chain, spot: float | None = None) -> GexProfile:
    """Compute dealer gamma exposure profile from an option chain.

    Convention (squeezemetrics / spotgamma):
        net_gex = sum_calls(gamma * OI * 100 * spot²)
                - sum_puts (gamma * OI * 100 * spot²)

    Positive → dealers net long gamma (suppressive).
    Negative → dealers net short gamma (amplifying).

    `spot` defaults to `chain.underlying_price`. Passing an explicit spot
    lets a caller probe GEX at hypothetical prices (the basis for finding
    zero-gamma in a future revision, once we have a BS regreek).
    """
    s = float(spot) if spot is not None else float(chain.underlying_price)
    s_squared = s * s

    by_strike: dict[float, float] = {}
    net_calls = 0.0
    net_puts = 0.0

    for c in chain.calls.values():
        contribution = c.gamma * c.open_interest * CONTRACT_MULTIPLIER * s_squared
        net_calls += contribution
        by_strike[c.strike] = by_strike.get(c.strike, 0.0) + contribution

    for p in chain.puts.values():
        contribution = -(p.gamma * p.open_interest * CONTRACT_MULTIPLIER * s_squared)
        net_puts += contribution
        by_strike[p.strike] = by_strike.get(p.strike, 0.0) + contribution

    return GexProfile(
        spot=s,
        net_gex=net_calls + net_puts,
        net_gex_calls=net_calls,
        net_gex_puts=net_puts,
        by_strike=by_strike,
    )
