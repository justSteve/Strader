"""Anchored volume profile — a profile that starts at an explicit anchor. [st-eo0]

``profile.py`` histograms a COMPLETED window from tick trades. This module
covers the other case Steve asked for (2026-08-11): a profile anchored at a
named moment — the prior RTH open — and running to *now*, spanning the prior
day session, the overnight, and the premarket as one distribution.

Why bars and not ticks
----------------------
The ES tick corpus captures 02:50–15:05 CT daily (measured 2026-08-11 across
08-07, 08-10, 08-11). That leaves an ~11h hole from 15:05 CT to 02:50 CT, and
the hole contains real volume — the 08-11 Mancini letter cites a low set at
12:30am CT, squarely inside it. A profile built from ticks alone would omit the
evening session without saying so, which is the failure mode a profile must
never have: a silent hole reads as "nobody traded there", the exact shape of an
LVN.

Schwab's 5-minute extended-hours candles cover the span continuously, so bars
are the source. The cost is granularity: a bar's volume is spread across the
prices it touched rather than placed where each contract actually printed. That
is how charting platforms build volume profile from bars, and it is honest at
this resolution — but it is an approximation, and the rendered page says so.

Refining the 02:50–15:05 CT portion with real ticks is a possible upgrade; it
would mix two volume semantics in one histogram, so it is deliberately not done
here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from market.entities.trade import Trade
from market.entities.volume_profile import VolumeProfile
from market.orderflow.profile import ProfileAccumulator
from market.signals.orderflow_config import PROFILE_BUCKET_TICKS, TICK

CENTRAL = ZoneInfo("America/Chicago")

# RTH open, US/Central. The anchor Steve chose (2026-08-11) over the 17:00 CT
# globex open: it matches how he reads the day session and lines up with
# Market Profile's Initial Balance.
RTH_OPEN_CT = time(8, 30)

# Fraction of total volume inside the value area. 70% is the Market Profile
# convention (roughly one standard deviation).
VALUE_AREA_COVERAGE = 0.70


@dataclass(frozen=True)
class ValueArea:
    """The price band holding ``coverage`` of the profile's volume."""

    val: float          # value area low  — bucket floor
    poc: float          # point of control — bucket floor
    vah: float          # value area high — bucket floor
    volume: int         # volume inside the band
    total: int          # profile total
    coverage: float     # requested fraction

    @property
    def achieved(self) -> float:
        return self.volume / self.total if self.total else 0.0

    @property
    def width(self) -> float:
        return self.vah - self.val


def anchor_utc(session_day, open_ct: time = RTH_OPEN_CT) -> datetime:
    """UTC datetime of ``session_day``'s cash open.

    Takes the session day (use ``paths.most_recent_session_day()`` so this
    cannot drift onto a different day than the corpus and the gate).
    """
    local = datetime.combine(session_day, open_ct, tzinfo=CENTRAL)
    return local.astimezone(timezone.utc)


def _bar_trades(bar: dict, bucket: float, symbol: str) -> Iterable[Trade]:
    """Spread one bar's volume across the buckets its range touched.

    Uniform across touched buckets, with the integer remainder assigned to the
    bucket holding the close — so the histogram total equals the bar total
    exactly and the leftover lands at the price the bar actually settled on
    rather than at an arbitrary edge.
    """
    vol = int(bar.get("volume") or 0)
    if vol <= 0:
        return ()
    lo, hi = float(bar["low"]), float(bar["high"])
    k_lo, k_hi = int(lo // bucket), int(hi // bucket)
    n = k_hi - k_lo + 1
    ts = datetime.fromtimestamp(bar["datetime"] / 1000, tz=timezone.utc).astimezone(CENTRAL)
    if n <= 1:
        return (Trade(ts=ts, symbol=symbol, instrument_id=0, price=lo, size=vol),)

    each, rem = divmod(vol, n)
    k_close = min(max(int(float(bar["close"]) // bucket), k_lo), k_hi)
    out: list[Trade] = []
    for k in range(k_lo, k_hi + 1):
        size = each + (rem if k == k_close else 0)
        if size:
            out.append(Trade(ts=ts, symbol=symbol, instrument_id=0,
                             price=k * bucket, size=size))
    return out


def build_profile_from_bars(bars: Sequence[dict], symbol: str = "/ES",
                            bucket_ticks: int = PROFILE_BUCKET_TICKS) -> VolumeProfile:
    """Histogram OHLCV bars into price buckets.

    Delegates to ``ProfileAccumulator`` so bar-sourced and tick-sourced
    profiles share ONE histogram implementation — the same parity guarantee
    profile.py's batch/live split rests on.
    """
    acc = ProfileAccumulator(bucket_ticks)
    for bar in bars:
        for t in _bar_trades(bar, bucket_ticks * TICK, symbol):
            acc.add(t)
    if not acc.n:
        raise ValueError("cannot build a profile from bars with no volume")
    return acc.build()


def value_area(profile: VolumeProfile,
               coverage: float = VALUE_AREA_COVERAGE) -> ValueArea:
    """POC/VAH/VAL for a profile.

    Expands outward from the POC one bucket at a time, always taking the
    heavier of the two neighbours, until ``coverage`` of total volume is
    enclosed. (The classic TPO method pairs two rows per step; single-row
    expansion is the common volume-profile variant and lands within a bucket
    of it.) Ties take the upper bucket.
    """
    vols, prices = profile.volumes, profile.prices
    total = profile.total
    if total <= 0:
        raise ValueError("cannot compute a value area for an empty profile")

    poc_i = max(range(len(vols)), key=lambda i: (vols[i], -prices[i]))
    lo = hi = poc_i
    covered = vols[poc_i]
    target = coverage * total
    while covered < target and (lo > 0 or hi < len(vols) - 1):
        up = vols[hi + 1] if hi < len(vols) - 1 else -1
        down = vols[lo - 1] if lo > 0 else -1
        if up >= down:
            hi += 1
            covered += vols[hi]
        else:
            lo -= 1
            covered += vols[lo]
    return ValueArea(val=prices[lo], poc=prices[poc_i], vah=prices[hi],
                     volume=covered, total=total, coverage=coverage)
