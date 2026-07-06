"""Session volume profile + POC/HVN/LVN level extraction (st-7d6, spec §2 Tier B).

Slow-moving structural context, not a per-tick signal: build the profile from
a COMPLETED window (v1 convention: the prior RTH session, PROFILE_WINDOW) and
consume its levels in the next session. Deterministic by construction — pure
functions of the trade list and the named config constants.

Node rules (research doc Q1.6):
  POC — highest-volume bucket (lower price wins ties).
  HVN — local maximum ≥ HVN_MIN_FRACTION × POC volume: accepted price.
  LVN — local minimum ≤ LVN_MAX_FRACTION × POC volume: rejected price; the
        location ``return_to_lvn`` reacts to. Direction-neutral — the
        emitted Level's support/resistance label is just position vs the
        reference price; the orderflow decides the branch (spec §3).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from market.entities.trade import Trade
from market.entities.volume_profile import VolumeProfile
from market.signals.types import Level
from market.signals.orderflow_config import (
    HVN_MIN_FRACTION,
    LVN_MAX_FRACTION,
    PROFILE_BUCKET_TICKS,
    PROFILE_WINDOW,
    TICK,
)

logger = logging.getLogger(__name__)

_BUCKET = PROFILE_BUCKET_TICKS * TICK


def build_profile(trades: Iterable[Trade], bucket_ticks: int = PROFILE_BUCKET_TICKS) -> VolumeProfile:
    """Histogram a completed window's trades into price buckets.

    Bucket floor = floor(price / bucket) × bucket, so a 1.0-pt bucket at
    7541.00 covers [7541.00, 7542.00). The bucket range is made contiguous
    (zero-volume buckets included) so local-extremum tests are well-defined.
    """
    trades = list(trades)
    if not trades:
        raise ValueError("cannot build a profile from zero trades")
    bucket = bucket_ticks * TICK
    vols: dict[int, int] = {}
    for t in trades:
        k = int(t.price // bucket)
        vols[k] = vols.get(k, 0) + t.size
    lo, hi = min(vols), max(vols)
    keys = range(lo, hi + 1)
    return VolumeProfile(
        symbol=trades[0].symbol,
        start_ts=trades[0].ts, end_ts=trades[-1].ts,
        bucket_pts=bucket,
        prices=tuple(round(k * bucket, 2) for k in keys),
        volumes=tuple(vols.get(k, 0) for k in keys),
    )


def _local_extrema(vols: tuple[int, ...]) -> tuple[list[int], list[int]]:
    """(maxima_idx, minima_idx) treating volume outside the traded range as
    zero — so an edge bucket can be a maximum (a session that closes on its
    high IS a node there) but never a minimum (a range end is not an LVN).
    Plateau handling: strict vs the left neighbor, non-strict vs the right,
    so flat tops/valleys yield their FIRST index — deterministic."""
    maxima, minima = [], []
    n = len(vols)
    for i in range(n):
        prev = vols[i - 1] if i > 0 else 0
        nxt = vols[i + 1] if i < n - 1 else 0
        if vols[i] > prev and vols[i] >= nxt:
            maxima.append(i)
        if 0 < i < n - 1 and vols[i] < prev and vols[i] <= nxt:
            minima.append(i)
    return maxima, minima


def profile_levels(
    profile: VolumeProfile,
    reference_price: float,
    ts: datetime | None = None,
) -> list[Level]:
    """Interpret a completed-window profile into Level signals.

    ``reference_price`` (e.g. today's open or last) classifies each node as
    support (below) or resistance (at/above). ``ts`` defaults to the
    profile's end — the moment the window completed and the level became
    knowable; pass the consuming session's open for live use.
    """
    ts = ts or profile.end_ts
    poc_vol = max(profile.volumes)
    maxima, minima = _local_extrema(profile.volumes)
    out: list[Level] = []

    def _emit(price: float, node: str, vol: int, conf: float) -> None:
        side = "support" if price < reference_price else "resistance"
        out.append(Level(
            timestamp=ts, source="orderflow.profile", confidence=conf,
            reason=(f"{node} @ {price:.2f} ({vol} contracts, "
                    f"{PROFILE_WINDOW} window {profile.start_ts.date()})"),
            price=price, level_type=side,
        ))

    _emit(profile.poc_price, "POC", poc_vol, 0.9)
    for i in maxima:
        p = profile.prices[i]
        if p != profile.poc_price and profile.volumes[i] >= HVN_MIN_FRACTION * poc_vol:
            _emit(p, "HVN", profile.volumes[i], 0.6)
    for i in minima:
        if 0 < profile.volumes[i] <= LVN_MAX_FRACTION * poc_vol:
            _emit(profile.prices[i], "LVN", profile.volumes[i], 0.6)
    logger.debug("profile_levels: %d levels from %s window (%d buckets)",
                 len(out), PROFILE_WINDOW, len(profile.prices))
    return out
