"""The join: an intent-dialect single becomes an FD0 bracket. [st-79z.3 × st-apzt]

Steve's ``go`` on a directional single (a long put or a long call — the
futures-proxy play, ``knowledge/singles-as-futures-proxy.md``) hands the chosen
contract to FD0. FD0 runs the budget backwards into a stop distance at the live
delta, sets the SPX-conditional trigger on the correct side of spot, and returns
the values that go into the TOS Order Rules gear. The dialect renders the entry
paste line; FD0 renders the exit that cannot be pasted.

Why only singles. FD0's whole mechanism is a budget-derived stop on a *directional*
long option — its risk is open until it is cut. A butterfly is defined-risk: the
most it loses is the debit paid, which the dialect already prints, so there is
nothing for a stop to protect and ``go`` stages it unbracketed. A vertical or a
condor the dialect does not price yet.

This module is pure and transmits nothing. It reads a chain snapshot and returns
an FD0 :class:`~strader.execution.compose.Ticket`; the order-transmission wall
(st-5ey) is not approached here.
"""
from __future__ import annotations

import datetime as dt

from market.entities.chain import Chain
from strader.execution.compose import Budget, Contract as Fd0Contract, Ticket, compose
from strader.intent.entities import Order


class NotBracketable(Exception):
    """The priced order is not a directional single, so FD0 has no stop to add.
    Carries why, so ``go`` can say it plainly rather than staging a silent gap."""


def _fd0_contract(chain: Chain, order: Order, *, day: dt.date | None = None) -> Fd0Contract:
    """The one leg of a single, pulled from the dialect's chain into FD0's shape.

    FD0's derivation is denominated in premium points and needs the leg's live
    bid/ask/delta. A single carries exactly one strike; the chain must hold it
    on the traded side, or there is no market to price the stop against.
    """
    strike = order.strikes[0]
    src = chain.calls if order.right == "CALL" else chain.puts
    from market.entities.chain import strike_key
    leg = src.get(strike_key(strike))
    if leg is None:
        raise NotBracketable(
            f"the chain snapshot has no {order.right.lower()} at {strike:g} to price a stop against"
        )
    dte = max(0, (chain.expiry - (day or chain.expiry)).days)
    return Fd0Contract(
        symbol=leg.symbol,
        strike=float(strike),
        bid_pts=float(leg.bid),
        ask_pts=float(leg.ask),
        delta=float(leg.delta),
        expiration=chain.expiry.isoformat(),
        dte=dte,
        right=order.right,
    )


def bracket(
    order: Order,
    chain: Chain,
    *,
    budget: Budget | None = None,
    spx_now: float | None = None,
    recent_minute_ranges_spx=(),
    day: dt.date | None = None,
) -> Ticket:
    """Build the FD0 bracket for a directional single.

    ``budget`` defaults to FD0's standing ceiling ($100, two attempts) — the
    first attempt's slice is what a fresh directional single risks. ``spx_now``
    defaults to the chain's underlying price, which is the level the stop is
    measured from.

    Raises :class:`NotBracketable` when the order is not a long single, and
    lets FD0's own :class:`CannotFund` through when the budget cannot fund the
    stop (its message carries the arithmetic).
    """
    if order.spread_type.upper() != "SINGLE":
        raise NotBracketable(
            f"a {order.spread_type.lower()} is defined-risk — its loss is the debit paid, "
            f"so FD0 has no stop to add. Only a directional single gets a bracket."
        )
    if order.action != "BUY" or order.quantity <= 0:
        raise NotBracketable("FD0 brackets long options only (the counter-chase stop)")

    contract = _fd0_contract(chain, order, day=day)
    return compose(
        [contract],
        spx_now if spx_now is not None else chain.underlying_price,
        budget or Budget(),
        contract=contract,
        lots=abs(order.quantity),
        recent_minute_ranges_spx=recent_minute_ranges_spx,
    )
