"""
Boundary layer: Mancini email + Schwab quote -> typed Session.

Mancini provides support/resistance levels via parsed email; Schwab
provides the day's price quote. This module bridges both into a single
Session entity.
"""
from __future__ import annotations
from datetime import date

from market.entities.level import Level
from market.entities.session import Session


def session_from_mancini(
    email: "ManciniEmail",
    quote: dict,
    session_date: date,
    vix: float,
    gex_posture: str,
) -> Session:
    """Build a Session from a parsed Mancini email and a Schwab quote dict.

    `quote` is from schwab client.get_quote('$SPX').json()['$SPX']['quote'].
    `gex_posture` is caller-supplied — not derivable from Mancini or quote.
    """
    from mancini.parser import Level as ManciniLevel

    def _bridge(ml: ManciniLevel, label: str) -> Level:
        return Level(price=ml.price, label=label, source="mancini", annotation=ml.annotation)

    supports    = tuple(_bridge(l, "support")    for l in email.support_levels)
    resistances = tuple(_bridge(l, "resistance") for l in email.resistance_levels)

    return Session(
        date=session_date,
        underlying_price=float(quote.get("mark", quote.get("lastPrice", 0.0))),
        open=float(quote.get("openPrice", 0.0)),
        high=float(quote.get("highPrice", 0.0)),
        low=float(quote.get("lowPrice", 0.0)),
        gex_posture=gex_posture,
        vix=vix,
        mancini_supports=supports,
        mancini_resistances=resistances,
    )
