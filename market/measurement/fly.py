"""Butterfly reconstruction from the OPRA trade tape — shared core. [st-745]

Pure logic used by both the single-day study CLI (`scripts/measurement/
fly_replay.py`) and the corpus batch (`scripts/measurement/fly_replay_batch.py`).
No argparse, no printing — just parsing + math so it's unit-testable.

A fly priced from the tape is `P(low) - 2*P(mid) + P(high)` using each leg's
last trade forward-filled. Parent symbology delivers every expiry, so the
expiry (YYMMDD) MUST be filtered — same strike at a different expiry prices
completely differently.
"""
from __future__ import annotations

import bisect
import gzip
import json
import re
from datetime import datetime, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")
_OCC = re.compile(r"(\d{6})([CP])(\d{8})$")


def parse_occ(symbol: str) -> tuple[str, str, float] | None:
    """`SPXW  260608C07485000` -> ('260608', 'C', 7485.0). None if unparseable."""
    if not symbol:
        return None
    m = _OCC.search(symbol.strip())
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3)) / 1000.0


def epoch_of(ts_event: str) -> float:
    """ISO ts (possibly nanosecond) -> epoch seconds (UTC), whole-second res."""
    return datetime.strptime(ts_event[:19], "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=UTC).timestamp()


def ct_epoch(d, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, _time(h, m), tzinfo=CENTRAL).timestamp()


def collect_window(corpus_path: Path, expiry: str, t0: float, t1: float
                   ) -> list[tuple[float, str, float, float]]:
    """Single pass over the tape -> [(epoch, right, strike, price)] for `expiry`
    within [t0, t1]. gz-aware. Used to derive both the parity settle and the
    fly legs without re-scanning."""
    out: list[tuple[float, str, float, float]] = []
    opener = gzip.open if str(corpus_path).endswith(".gz") else open
    with opener(corpus_path, "rt") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            data = row.get("data", {})
            parsed = parse_occ(data.get("symbol") or "")
            if not parsed:
                continue
            exp, r, strike = parsed
            if exp != expiry:
                continue
            prov = row.get("provenance", {})
            ts = prov.get("ts_event") or row.get("ts_pull_utc")
            price = data.get("price")
            if ts is None or price is None:
                continue
            ep = epoch_of(ts)
            if t0 <= ep <= t1:
                out.append((ep, r, strike, float(price)))
    return out


def legs_from_window(window, strikes: set[float], right: str
                     ) -> dict[float, list[tuple[float, float]]]:
    legs: dict[float, list[tuple[float, float]]] = {k: [] for k in strikes}
    for ep, r, strike, price in window:
        if r == right and strike in legs:
            legs[strike].append((ep, price))
    for k in legs:
        legs[k].sort()
    return legs


def _last_price_at(trades: list[tuple[float, float]], ep: float) -> float | None:
    if not trades:
        return None
    i = bisect.bisect_right([t for t, _ in trades], ep) - 1
    return trades[i][1] if i >= 0 else None


def fly_series(legs, k_low: float, k_mid: float, k_high: float,
               t0: float, t1: float, bin_seconds: int = 30
               ) -> list[tuple[float, float]]:
    """Forward-filled fly price over [t0,t1]. Bins missing any leg are skipped."""
    out: list[tuple[float, float]] = []
    ep = t0
    while ep <= t1:
        pl = _last_price_at(legs.get(k_low, []), ep)
        pm = _last_price_at(legs.get(k_mid, []), ep)
        ph = _last_price_at(legs.get(k_high, []), ep)
        if pl is not None and pm is not None and ph is not None:
            out.append((ep, round(pl - 2 * pm + ph, 2)))
        ep += bin_seconds
    return out


def entry_sweep(series, settle_value: float, entry_eps) -> list[dict]:
    """Per candidate entry: price paid, worst drawdown below it before window
    end, settle P&L."""
    rows = []
    for e in entry_eps:
        after = [(t, p) for t, p in series if t >= e]
        if not after:
            continue
        entry = after[0][1]
        drawdown = max(0.0, entry - min(p for _, p in after))
        rows.append({
            "entry_ct": datetime.fromtimestamp(e, CENTRAL).strftime("%H:%M"),
            "entry_price": round(entry, 2),
            "max_drawdown": round(drawdown, 2),
            "settle_value": round(settle_value, 2),
            "pnl_to_settle": round(settle_value - entry, 2),
        })
    return rows


def fly_intrinsic(settle_spot: float, k_low: float, k_mid: float,
                  k_high: float, right: str) -> float:
    def opt(k):
        return max(0.0, settle_spot - k) if right == "C" else max(0.0, k - settle_spot)
    return opt(k_low) - 2 * opt(k_mid) + opt(k_high)


def settle_parity(window, near_lo: float, near_hi: float) -> float | None:
    """SPX-at-settle via put-call parity: S = K + C - P, taken at the most-ATM
    strike (min |C-P|) using each strike's latest C and P print in
    [near_lo, near_hi]. Self-contained — no underlying feed needed."""
    best_c: dict[float, tuple[float, float]] = {}
    best_p: dict[float, tuple[float, float]] = {}
    for ep, r, strike, price in window:
        if not (near_lo <= ep <= near_hi):
            continue
        book = best_c if r == "C" else best_p
        if strike not in book or ep > book[strike][0]:
            book[strike] = (ep, price)
    cands = []
    for k in set(best_c) & set(best_p):
        c, p = best_c[k][1], best_p[k][1]
        cands.append((abs(c - p), k + c - p))  # (ATM-ness, implied S)
    if not cands:
        return None
    cands.sort()
    return cands[0][1]
