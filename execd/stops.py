"""The protective stop — the number that survives this box dying. [st-eznu]

FD0 derives its exit as an **SPX level** (``strader/execution/compose.py``:
the budget runs backwards into ``stop_distance_spx``, and ``stop_trigger``
puts it above spot for a long put and below for a long call). That is the
right instrument to think in — the arithmetic is denominated in index points —
but SPX is not the thing being sold, so an SPX level cannot rest at the broker.

So there are two stops, and they are not redundant:

1. **The resting stop on the option**, placed the moment a fill comes back.
   Its price is this module's job: the SPX distance walked through the option's
   delta into premium points. It is the stop that is still standing if this box
   OOMs at three in the morning, which has happened.
2. **The SPX-mark exit loop**, run by the service while it is alive
   (``ExecService.observe``). It watches the index and sends a market close the
   moment the level trades, then cancels the resting stop.

The first is a floor under the second, not a substitute for it. Delta moves,
so the option-price stop drifts away from the SPX level it was derived from as
the day goes on; the live loop is what stays accurate. Belt, then braces.

**Rounding.** The stop price is rounded *up* to the tick — toward the fill,
i.e. the tighter of the two valid ticks. Rounding down would let the realized
loss sit up to one tick beyond the budget the stop distance was derived from,
and the budget is a ceiling rather than a target. This is the same asymmetry
FD0 applies to a buy limit and for the same kind of reason
(``compose.py:463-472``): one tick against you is cheap, the bound being wrong
is not.

**The tick is not one number.** SPX options quote in $0.05 below $3.00 and in
$0.10 at and above it. Measured, not remembered (st-pohq, 2026-09-04,
``docs/measurement/spx-option-tick-2026-09-04.md``): in a live $SPX chain of
160 contracts, every one of the 205 quoted sides at or above $3.00 sat on the
0.10 grid and none needed 0.05; below $3.00 half of them did. A stop resting
at 3.05 is a stop the exchange refuses under a live position, which is the
one state this module exists to prevent — so :func:`tick_for` picks the grid
by the price, and a stop that rounds across $3.00 is re-rounded onto the
coarser grid.
"""

from __future__ import annotations

import math

PREMIUM_TICK_PTS = 0.05          # the finer grid, below $3.00
PREMIUM_TICK_PTS_ABOVE_3 = 0.10  # at and above $3.00
TICK_BOUNDARY_PTS = 3.00
CONTRACT_MULTIPLIER = 100


def tick_for(pts: float) -> float:
    """The quoting increment in force at this premium."""
    return PREMIUM_TICK_PTS_ABOVE_3 if float(pts) >= TICK_BOUNDARY_PTS else PREMIUM_TICK_PTS


def _ceil_to(pts: float, tick: float) -> float:
    return round(math.ceil(round(pts / tick, 6)) * tick, 2)


def _floor_to(pts: float, tick: float) -> float:
    return round(math.floor(round(pts / tick, 6)) * tick, 2)


def _round_up_to_tick(pts: float, tick: float = PREMIUM_TICK_PTS) -> float:
    """Up to the finer grid first; if that lands at or above the boundary,
    up again to the coarser one. 2.96 → 3.00, 3.01 → 3.10, 3.10 → 3.10."""
    price = _ceil_to(pts, tick)
    if price >= TICK_BOUNDARY_PTS:
        price = _ceil_to(price, max(tick, PREMIUM_TICK_PTS_ABOVE_3))
    return price


def stop_distance_spx(spx_now: float, stop_spx: float) -> float:
    """How far the index has to travel to reach the cut. Unsigned — the sign
    lives in ``exit_triggered``, which knows which way the option loses."""
    return abs(float(spx_now) - float(stop_spx))


def premium_at_stop(fill_px: float, delta_abs: float, spx_now: float,
                    stop_spx: float) -> float:
    """The option's price when SPX reaches the stop, by the local delta.

    A first-order estimate and honestly so: gamma means a long option decays
    toward the stop more slowly than delta alone predicts, so this errs on the
    side of a stop that triggers slightly early. That is the direction to err."""
    return float(fill_px) - stop_distance_spx(spx_now, stop_spx) * abs(float(delta_abs))


def protective_stop_price(fill_px: float, delta_abs: float, spx_now: float,
                          stop_spx: float, tick: float = PREMIUM_TICK_PTS) -> float:
    """The price of the resting SELL stop on the option itself.

    Raises ``ValueError`` rather than guessing when the inputs cannot produce a
    stop — a fill with no protective stop is the one state this service must
    not reach quietly."""
    fill_px = float(fill_px)
    delta_abs = abs(float(delta_abs))
    if fill_px <= 0:
        raise ValueError(f"fill price must be positive, not {fill_px}")
    if not (0 < delta_abs <= 1):
        raise ValueError(f"delta must be within (0, 1], not {delta_abs}")
    if stop_distance_spx(spx_now, stop_spx) <= 0:
        raise ValueError(
            f"stop_spx {stop_spx} is the current index level — no distance to derive a stop from"
        )

    price = _round_up_to_tick(premium_at_stop(fill_px, delta_abs, spx_now, stop_spx), tick)

    # Two clamps, both for real cases. A stop distance wide enough to take the
    # option to zero is a stop that would never trigger, so it rests one tick
    # above nothing and the position runs to expiry or the live loop instead.
    # A stop at or above the fill would fire on the first tick of spread noise;
    # the cap is one tick below the fill, on the grid in force there.
    price = max(price, tick)
    fill_tick = max(tick, tick_for(fill_px))
    cap = round(fill_px - fill_tick, 2)
    cap = _floor_to(cap, max(tick, tick_for(cap))) if cap > 0 else cap
    price = min(price, cap)
    if price < tick:
        raise ValueError(
            f"a {fill_px:.2f} fill leaves no room for a stop above the {tick:.2f} tick"
        )
    return round(price, 2)


def risk_usd(fill_px: float, stop_price: float, qty: int = 1) -> float:
    """What the resting stop caps the loss at, before fees, in dollars."""
    return round((float(fill_px) - float(stop_price)) * CONTRACT_MULTIPLIER * int(qty), 2)


def exit_triggered(right: str, spx: float, stop_spx: float) -> bool:
    """Has the index reached the cut?

    A long call loses as SPX falls, so its stop sits below spot and triggers on
    the way down; a long put is the mirror. Direction-blind arithmetic with a
    direction-aware trigger — the same split ``compose.stop_trigger`` makes."""
    r = (right or "").upper()
    if r in ("C", "CALL"):
        return float(spx) <= float(stop_spx)
    if r in ("P", "PUT"):
        return float(spx) >= float(stop_spx)
    raise ValueError(f"right must be CALL or PUT, not {right!r}")


def stop_is_consistent(right: str, spx_now: float, stop_spx: float) -> bool:
    """Is the stop on the losing side of spot? A call stop above the market or
    a put stop below it is already triggered at compose time — a transposed
    sign, not a trade. The service refuses these before it sends."""
    return not exit_triggered(right, spx_now, stop_spx)
