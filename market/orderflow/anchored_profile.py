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


@dataclass(frozen=True)
class SplitProfile:
    """A profile with buy- and sell-aggressor volume kept apart. [st-6gs3]

    Databento's trades schema carries the aggressor on every print (side 'B' =
    lifted the ask, 'A' = hit the bid), and it is fully populated — 114,043 ES
    prints on 2026-08-11, none unknown. So the buy/sell split costs nothing
    extra to compute and is exact, unlike the bar path where a bar's volume has
    to be smeared across the prices it touched with no idea who was aggressing.

    This is what TradingView renders as an up/down-volume profile.
    """

    symbol: str
    start_ts: datetime
    end_ts: datetime
    bucket_pts: float
    prices: tuple[float, ...]
    buy_volumes: tuple[int, ...]
    sell_volumes: tuple[int, ...]

    def __post_init__(self) -> None:
        if not (len(self.prices) == len(self.buy_volumes) == len(self.sell_volumes)):
            raise ValueError("prices, buy_volumes and sell_volumes must be parallel")

    @property
    def volumes(self) -> tuple[int, ...]:
        return tuple(b + s for b, s in zip(self.buy_volumes, self.sell_volumes))

    @property
    def deltas(self) -> tuple[int, ...]:
        """Buy minus sell per bucket — where aggression net-leaned."""
        return tuple(b - s for b, s in zip(self.buy_volumes, self.sell_volumes))

    @property
    def total(self) -> int:
        return sum(self.volumes)

    @property
    def delta(self) -> int:
        return sum(self.buy_volumes) - sum(self.sell_volumes)

    def as_volume_profile(self) -> VolumeProfile:
        """Collapse the split so POC/value-area code works unchanged."""
        return VolumeProfile(
            symbol=self.symbol, start_ts=self.start_ts, end_ts=self.end_ts,
            bucket_pts=self.bucket_pts, prices=self.prices, volumes=self.volumes,
        )


def build_split_profile(trades: Iterable[Trade],
                        bucket_ticks: int = 1) -> SplitProfile:
    """Histogram real prints into buckets, keeping the aggressor sides apart.

    Default bucket is ONE tick — the native resolution of the instrument. The
    bar path defaults coarser (4 ticks) because a smeared bar cannot support
    fine buckets honestly; real prints can.

    Unknown-aggressor prints ('N') are counted in the total by splitting them
    evenly, so the histogram total always equals the traded total. On ES this
    is a no-op — Databento classifies every print.
    """
    bucket = bucket_ticks * TICK
    buys: dict[int, int] = {}
    sells: dict[int, int] = {}
    symbol: str | None = None
    first_ts = last_ts = None
    n = 0
    for t in trades:
        k = int(t.price // bucket)
        if t.side == "B":
            buys[k] = buys.get(k, 0) + t.size
        elif t.side == "A":
            sells[k] = sells.get(k, 0) + t.size
        else:
            half = t.size / 2
            buys[k] = buys.get(k, 0) + int(half)
            sells[k] = sells.get(k, 0) + t.size - int(half)
        if n == 0:
            symbol, first_ts = t.symbol, t.ts
        last_ts = t.ts
        n += 1
    if not n:
        raise ValueError("cannot build a profile from zero trades")
    lo, hi = min(min(buys or {0: 0}), min(sells or {0: 0})), \
             max(max(buys or {0: 0}), max(sells or {0: 0}))
    keys = range(lo, hi + 1)
    return SplitProfile(
        symbol=symbol, start_ts=first_ts, end_ts=last_ts, bucket_pts=bucket,
        prices=tuple(round(k * bucket, 4) for k in keys),
        buy_volumes=tuple(buys.get(k, 0) for k in keys),
        sell_volumes=tuple(sells.get(k, 0) for k in keys),
    )


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
