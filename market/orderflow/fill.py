"""Intra-bar fill steps — honest sub-bar tape slices for progressive render.

Moved out of ``scripts/orderflow_drill.py`` when the live feeder needed the
same function [st-re1o]. Both the replay drill and the live footprint render
bars by accumulating these chunks, so they must be produced by one
implementation or the two surfaces would animate differently from identical
tape — the visible half of the spec §5 parity guarantee.

Steve's stated preference (see the drills-as-code convention): show the bar's
progression as trades land rather than popping in fully-formed columns. These
are real tape slices, not interpolation.
"""
from __future__ import annotations

#: Progressive-build chunks per bar (st-9lh) — real tape slices, not animation.
#: 8 → 16 on 2026-08-18 [st-9olq]: at 8 a slow RTH bar drilled at 2× repainted
#: every 8-13 s (08-12 drill: p90 7.9 s, max 13.3 s) and read as a stall; Steve:
#: "smoother is better". Doubling halves every gap; a drill page grows ~40%
#: (08-12: 626 KB → ~870 KB), all of it tape, all of it local.
FILL_STEPS = 16


def bar_fill_steps(trades, bars, n_steps: int = FILL_STEPS) -> list[list]:
    """Per bar: equal-volume cumulative fill chunks for progressive rendering.

    The bar's own trades are split into ``n_steps`` equal-volume chunks (a whole
    trade lands in the chunk it completes, mirroring the bar straddle rule).
    Each chunk is ``[close_price, elapsed_seconds, [[price, sellAggrAdd,
    buyAggrAdd], ...]]`` — additive deltas the template accumulates into partial
    cells. Side "N" trades advance volume/close/clock only, matching the cells
    convention.

    ``trades`` must start at the first trade of ``bars[0]``; the walk is
    positional. The live feeder hands in exactly one bar's trades at a time.
    """
    out: list[list] = []
    ti = 0
    for b in bars:
        vol = 0
        bar_trades = []
        while ti < len(trades) and vol < b.volume:
            t = trades[ti]
            ti += 1
            vol += t.size
            bar_trades.append(t)
        steps, adds = [], {}
        done_vol, k = 0, 1
        for t in bar_trades:
            done_vol += t.size
            if t.side != "N":
                a = adds.setdefault(t.price, [0, 0])
                a[0 if t.side == "A" else 1] += t.size
            if done_vol >= b.volume * k / n_steps and k <= n_steps:
                elapsed = (t.ts - b.start_ts).total_seconds()
                steps.append([t.price, round(elapsed, 1),
                              [[p, sa, ba] for p, (sa, ba) in sorted(adds.items())]])
                adds = {}
                while done_vol >= b.volume * k / n_steps and k <= n_steps:
                    k += 1
        out.append(steps)
    return out


_RTH_OPEN_CT = (8, 30)


def session_delta(bar_trades, day=None) -> int:
    """The bar's contribution to the cash session's delta: buy minus sell
    size over its trades at or after 08:30 CT. [st-v69l]

    The engine's CVD resets at the first trade at or after 08:30
    (``OrderflowEngine._roll_session``), so a bar straddling the open carries
    its post-open trades into the session. The page summed whole bars that
    START at or after 08:30 instead — the straddle bar alone was -352 on
    09-30, and "Session Δ" read 108-451 contracts away from the CVD the
    divergence lines quote. Carrying this per bar makes them one number.

    ``day`` is the session's date; trades from its 08:30 CT onward count,
    past midnight too, as the engine's CVD does until the next open.
    Without it the bar's own first trade names the day.
    """
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    ct = ZoneInfo("America/Chicago")
    out = 0
    opened = None
    for t in bar_trades:
        lt = t.ts.astimezone(ct)
        if opened is None:
            opened = datetime.combine(day or lt.date(), time(*_RTH_OPEN_CT), ct)
        if lt < opened:
            continue
        if t.side == "B":
            out += t.size
        elif t.side == "A":
            out -= t.size
    return out


def bar_trade_slices(trades, bars):
    """Each bar's own trades — the positional walk ``bar_fill_steps`` and the
    live feeder's ``take_bar_trades`` use, so the slices agree."""
    ti = 0
    for b in bars:
        vol, start = 0, ti
        while ti < len(trades) and vol < b.volume:
            vol += trades[ti].size
            ti += 1
        yield trades[start:ti]
