"""
Tape Reconstruction — build per-day 1-minute tape from trough-10 to close.

Phase 1-2 of the post-entry tape study (st-745 reframe).
Produces a standardized tape profile for each V-day (or any day):
  - ES: 1-minute OHLC, VWAP, trade count
  - OPRA: volume (total, 0DTE, non-0DTE, puts, calls), premium flow, P/C ratio
  - Time-normalized volume using the 246-day per-minute baseline
  - Scare dip detection (pullbacks > threshold during recovery)
  - Bounce metrics (velocity, time-to-50%, time-to-75%)

Usage:
    .venv/bin/python scripts/measurement/tape_reconstruction.py
    .venv/bin/python scripts/measurement/tape_reconstruction.py --date 2026-05-21
    .venv/bin/python scripts/measurement/tape_reconstruction.py --all-v-days
    .venv/bin/python scripts/measurement/tape_reconstruction.py --all-v-days --neg-a
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

STRADER_ROOT = Path("/root/projects/Strader")
DATA_DIR = STRADER_ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
MEASUREMENT_DIR = DATA_DIR / "measurement"
OUTPUT_DIR = MEASUREMENT_DIR / "tape_profiles"

CENTRAL = ZoneInfo("America/Chicago")

CONFIRMED_V_DAYS = [
    '2025-08-11', '2025-09-17', '2025-09-29', '2025-10-13', '2025-10-29',
    '2025-11-17', '2026-01-30', '2026-02-18', '2026-03-30', '2026-04-01',
    '2026-04-08', '2026-05-08', '2026-05-21',
]

CLOSE_MINUTE = 120  # minute 120 = 15:00 CT (relative to 13:00)


def parse_iso_timestamp(ts_str: str) -> datetime:
    if "." in ts_str:
        base, frac_and_tz = ts_str.split(".", 1)
        frac = ""
        tz_part = ""
        i = 0
        while i < len(frac_and_tz) and frac_and_tz[i].isdigit():
            frac += frac_and_tz[i]
            i += 1
        tz_part = frac_and_tz[i:]
        frac = frac[:6].ljust(6, "0")
        ts_str = f"{base}.{frac}{tz_part}"
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def minute_since_1300(ts: datetime) -> int:
    ct = ts.astimezone(CENTRAL)
    return (ct.hour - 13) * 60 + ct.minute


def parse_occ_symbol(symbol: str) -> dict | None:
    """Parse OCC option symbol. Returns dict with expiry, strike, pc, or None."""
    symbol = symbol.strip()
    if len(symbol) < 21:
        return None
    try:
        root = symbol[:6].strip()
        exp_str = symbol[6:12]
        pc = symbol[12]
        strike_str = symbol[13:21]
        expiry = datetime.strptime(exp_str, "%y%m%d").date()
        strike = int(strike_str) / 1000.0
        return {"root": root, "expiry": expiry, "pc": pc, "strike": strike}
    except (ValueError, IndexError):
        return None


def compute_dte(trade_date: _date, expiry: _date) -> int:
    return (expiry - trade_date).days


@dataclass
class ESMinuteBar:
    minute: int  # minutes since 13:00 CT
    open_p: float = 0.0
    high_p: float = 0.0
    low_p: float = float('inf')
    close_p: float = 0.0
    vwap_p: float = 0.0
    trade_count: int = 0
    total_size: int = 0
    _price_x_size: float = 0.0

    def add_trade(self, price: float, size: int):
        if self.trade_count == 0:
            self.open_p = price
        self.high_p = max(self.high_p, price)
        self.low_p = min(self.low_p, price)
        self.close_p = price
        self.trade_count += 1
        self.total_size += size
        self._price_x_size += price * size

    def finalize(self):
        if self.total_size > 0:
            self.vwap_p = self._price_x_size / self.total_size
        if self.low_p == float('inf'):
            self.low_p = 0.0


@dataclass
class OPRAMinuteBar:
    minute: int
    total_volume: int = 0
    put_volume: int = 0
    call_volume: int = 0
    dte0_volume: int = 0
    dte_nonzero_volume: int = 0
    put_premium: float = 0.0
    call_premium: float = 0.0
    total_premium: float = 0.0
    trade_count: int = 0
    total_size_x_price: float = 0.0
    large_trade_count: int = 0  # trades >= 50 contracts

    @property
    def pc_volume_ratio(self) -> float:
        if self.call_volume == 0:
            return float('inf') if self.put_volume > 0 else 1.0
        return self.put_volume / self.call_volume

    @property
    def dte0_fraction(self) -> float:
        if self.total_volume == 0:
            return 0.0
        return self.dte0_volume / self.total_volume

    @property
    def total_premium_dollars(self) -> float:
        return self.total_premium

    @property
    def avg_trade_size(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return self.total_volume / self.trade_count


@dataclass
class StrikeTracker:
    """Track premium for specific strikes over time."""
    strike: float
    pc: str  # P or C
    dte: int
    minute_prices: dict = field(default_factory=dict)  # minute -> list of (price, size)

    def add_trade(self, minute: int, price: float, size: int):
        if minute not in self.minute_prices:
            self.minute_prices[minute] = []
        self.minute_prices[minute].append((price, size))

    def vwap_at_minute(self, minute: int) -> float | None:
        if minute not in self.minute_prices:
            return None
        trades = self.minute_prices[minute]
        total_pxs = sum(p * s for p, s in trades)
        total_s = sum(s for _, s in trades)
        if total_s == 0:
            return None
        return total_pxs / total_s

    def last_price_at_minute(self, minute: int) -> float | None:
        if minute not in self.minute_prices:
            return None
        return self.minute_prices[minute][-1][0]


@dataclass
class ScaredDip:
    """A pullback during the recovery phase."""
    start_minute: int
    start_price: float
    low_minute: int
    low_price: float
    end_minute: int  # when price recovers to start_price
    end_price: float
    depth_pts: float
    duration_minutes: int
    recovery_so_far_pts: float  # how much price had recovered from trough before this dip
    depth_pct_of_recovery: float  # depth as % of recovery-so-far


@dataclass
class TapeProfile:
    date: str
    label: str  # v_down, continuation, etc.
    trough_minute: int
    trough_price: float
    close_price: float
    depth_pts: float
    recovery_pts: float
    latr_20: float

    es_bars: dict[int, ESMinuteBar] = field(default_factory=dict)
    opra_bars: dict[int, OPRAMinuteBar] = field(default_factory=dict)
    strike_trackers: dict[str, StrikeTracker] = field(default_factory=dict)
    scare_dips: list[ScaredDip] = field(default_factory=list)

    # Bounce metrics
    bounce_velocity_5min: float = 0.0  # pts/min in first 5 min
    bounce_velocity_10min: float = 0.0
    time_to_50pct: int | None = None  # minutes to recover 50% of depth
    time_to_75pct: int | None = None
    time_to_100pct: int | None = None
    max_intra_recovery_drawdown: float = 0.0  # deepest scare dip

    # Volume climax metrics (from old study, recomputed here)
    volume_climax_minute: int | None = None
    volume_climax_ratio: float = 0.0
    post_climax_decay_rate: float = 0.0


def load_volume_baseline() -> dict[int, float]:
    """Load the 246-day per-minute volume baseline.

    Returns dict mapping minute-since-13:00 -> expected volume.
    Falls back to computing from the plan's table if no cached file exists.
    """
    baseline_path = MEASUREMENT_DIR / "volume_baseline_per_minute.json"
    if baseline_path.exists():
        with open(baseline_path) as f:
            raw = json.load(f)
        return {int(k): v for k, v in raw.items()}

    # Fallback: use the 10-minute averages from the plan, spread across minutes
    ten_min_avgs = {
        0: 7754, 10: 7818, 20: 7109, 30: 7625, 40: 7381, 50: 8135,
        60: 8330, 70: 8339, 80: 8103, 90: 9566, 100: 10224, 110: 14530,
    }
    baseline = {}
    for start_min, avg_per_min in ten_min_avgs.items():
        for m in range(start_min, min(start_min + 10, 120)):
            baseline[m] = avg_per_min
    return baseline


def build_es_tape(es_path: Path, start_minute: int, end_minute: int) -> dict[int, ESMinuteBar]:
    """Build 1-minute ES bars from start_minute to end_minute (inclusive)."""
    bars = {}
    for m in range(start_minute, end_minute + 1):
        bars[m] = ESMinuteBar(minute=m)

    with open(es_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = rec.get("provenance", {}).get("ts_event")
            if not ts_str:
                continue
            try:
                ts = parse_iso_timestamp(ts_str)
            except (ValueError, IndexError):
                continue

            m = minute_since_1300(ts)
            if m < start_minute or m > end_minute:
                continue

            data = rec.get("data", {})
            price = data.get("price")
            size = data.get("size", 1)
            action = data.get("action", "")
            if price is None or action != "T":
                continue

            bars[m].add_trade(price, size)

    for bar in bars.values():
        bar.finalize()
    return bars


def build_opra_tape(opra_path: Path, trade_date: _date,
                    start_minute: int, end_minute: int,
                    trough_price: float,
                    track_strikes: list[float] | None = None
                    ) -> tuple[dict[int, OPRAMinuteBar], dict[str, StrikeTracker]]:
    """Build 1-minute OPRA bars and optionally track specific strikes."""
    bars = {}
    for m in range(start_minute, end_minute + 1):
        bars[m] = OPRAMinuteBar(minute=m)

    trackers = {}
    if track_strikes:
        for strike in track_strikes:
            for pc in ("C", "P"):
                key = f"{pc}{strike:.0f}_0DTE"
                trackers[key] = StrikeTracker(strike=strike, pc=pc, dte=0)

    with open(opra_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = rec.get("provenance", {}).get("ts_event")
            if not ts_str:
                continue
            try:
                ts = parse_iso_timestamp(ts_str)
            except (ValueError, IndexError):
                continue

            m = minute_since_1300(ts)
            if m < start_minute or m > end_minute:
                continue

            data = rec.get("data", {})
            symbol = data.get("symbol", "")
            if not symbol.startswith("SPXW"):
                continue

            size = data.get("size", 0)
            price = data.get("price", 0.0)
            if size <= 0 or price <= 0:
                continue

            parsed = parse_occ_symbol(symbol)
            if parsed is None:
                continue

            dte = compute_dte(trade_date, parsed["expiry"])
            pc = parsed["pc"]
            strike = parsed["strike"]
            premium = size * price * 100  # dollar premium

            bar = bars[m]
            bar.total_volume += size
            bar.trade_count += 1
            bar.total_premium += premium

            if pc == "P":
                bar.put_volume += size
                bar.put_premium += premium
            else:
                bar.call_volume += size
                bar.call_premium += premium

            if dte == 0:
                bar.dte0_volume += size
            else:
                bar.dte_nonzero_volume += size

            if size >= 50:
                bar.large_trade_count += 1

            # Track specific strikes
            if track_strikes and dte == 0:
                key = f"{pc}{strike:.0f}_0DTE"
                if key in trackers:
                    trackers[key].add_trade(m, price, size)

    return bars, trackers


def detect_scare_dips(es_bars: dict[int, ESMinuteBar],
                      trough_minute: int, trough_price: float,
                      threshold_pts: float = 2.0) -> list[ScaredDip]:
    """Find all pullbacks > threshold during the recovery phase."""
    dips = []
    sorted_minutes = sorted(m for m in es_bars if m >= trough_minute and es_bars[m].trade_count > 0)
    if not sorted_minutes:
        return dips

    running_high = trough_price
    running_high_minute = trough_minute
    in_dip = False
    dip_start_minute = 0
    dip_start_price = 0.0
    dip_low = float('inf')
    dip_low_minute = 0

    for m in sorted_minutes:
        bar = es_bars[m]
        if bar.trade_count == 0:
            continue

        close = bar.close_p
        low = bar.low_p

        if close > running_high:
            if in_dip:
                recovery_so_far = running_high - trough_price
                depth = dip_start_price - dip_low
                depth_pct = (depth / recovery_so_far * 100) if recovery_so_far > 0 else 0
                dips.append(ScaredDip(
                    start_minute=dip_start_minute,
                    start_price=dip_start_price,
                    low_minute=dip_low_minute,
                    low_price=dip_low,
                    end_minute=m,
                    end_price=close,
                    depth_pts=depth,
                    duration_minutes=m - dip_start_minute,
                    recovery_so_far_pts=recovery_so_far,
                    depth_pct_of_recovery=depth_pct,
                ))
                in_dip = False
            running_high = close
            running_high_minute = m

        if low < running_high - threshold_pts and not in_dip:
            in_dip = True
            dip_start_minute = running_high_minute
            dip_start_price = running_high
            dip_low = low
            dip_low_minute = m

        if in_dip and low < dip_low:
            dip_low = low
            dip_low_minute = m

    # Close out any dip still open at end of data
    if in_dip:
        last_m = sorted_minutes[-1]
        recovery_so_far = running_high - trough_price
        depth = dip_start_price - dip_low
        depth_pct = (depth / recovery_so_far * 100) if recovery_so_far > 0 else 0
        dips.append(ScaredDip(
            start_minute=dip_start_minute,
            start_price=dip_start_price,
            low_minute=dip_low_minute,
            low_price=dip_low,
            end_minute=last_m,
            end_price=es_bars[last_m].close_p,
            depth_pts=depth,
            duration_minutes=last_m - dip_start_minute,
            recovery_so_far_pts=recovery_so_far,
            depth_pct_of_recovery=depth_pct,
        ))

    return dips


def compute_bounce_metrics(es_bars: dict[int, ESMinuteBar],
                           trough_minute: int, trough_price: float,
                           depth: float) -> dict:
    """Compute bounce velocity and time-to-recovery metrics."""
    metrics = {}
    sorted_minutes = sorted(m for m in es_bars if m >= trough_minute and es_bars[m].trade_count > 0)

    # Bounce velocity
    for window, label in [(5, "5min"), (10, "10min"), (15, "15min")]:
        target_min = trough_minute + window
        candidates = [m for m in sorted_minutes if m <= target_min]
        if candidates:
            price_at_window = es_bars[candidates[-1]].close_p
            recovery = price_at_window - trough_price
            metrics[f"bounce_velocity_{label}"] = recovery / window
            metrics[f"bounce_recovery_{label}_pts"] = recovery
        else:
            metrics[f"bounce_velocity_{label}"] = 0.0
            metrics[f"bounce_recovery_{label}_pts"] = 0.0

    # Time to recover X% of depth
    for pct, label in [(50, "50pct"), (75, "75pct"), (100, "100pct")]:
        target_price = trough_price + depth * (pct / 100.0)
        found = False
        for m in sorted_minutes:
            if es_bars[m].high_p >= target_price:
                metrics[f"time_to_{label}"] = m - trough_minute
                found = True
                break
        if not found:
            metrics[f"time_to_{label}"] = None

    return metrics


def build_tape_profile(day_info: dict, baseline: dict[int, float],
                       track_strikes: list[float] | None = None) -> TapeProfile | None:
    """Build a complete tape profile for one day."""
    date_str = day_info["date"]
    corpus_path = CORPUS_DIR / date_str
    es_path = corpus_path / "databento_glbx_es.jsonl"
    opra_path = corpus_path / "databento_opra.jsonl"

    if not es_path.exists() or not opra_path.exists():
        print(f"  SKIP {date_str}: missing corpus data", file=sys.stderr)
        return None

    trough_t_str = day_info.get("trough_t", "")
    if not trough_t_str:
        print(f"  SKIP {date_str}: no trough timestamp", file=sys.stderr)
        return None

    trough_dt = datetime.fromisoformat(trough_t_str)
    ct_trough = trough_dt.astimezone(CENTRAL)
    trough_minute = (ct_trough.hour - 13) * 60 + ct_trough.minute

    trough_price = day_info.get("trough_p", 0.0)
    close_price = day_info.get("close_p", 0.0)
    vwap_p = day_info.get("vwap_p", 0.0)

    v_down = day_info.get("v_down", {})
    depth = v_down.get("depth", vwap_p - trough_price)
    recovery = v_down.get("recovery", close_price - trough_price)

    label = day_info.get("label", "unknown")
    latr_20 = day_info.get("latr_20", 0.0) or 0.0

    start_minute = max(0, trough_minute - 10)
    end_minute = CLOSE_MINUTE

    print(f"  Building tape for {date_str} (trough at minute {trough_minute}, "
          f"price {trough_price:.2f}, depth {depth:.1f}pts)...", file=sys.stderr)

    trade_date = _date.fromisoformat(date_str)

    # Auto-select strikes to track if not specified
    if track_strikes is None:
        rounded = round(trough_price / 5) * 5
        track_strikes = [rounded - 10, rounded - 5, rounded, rounded + 5, rounded + 10]

    es_bars = build_es_tape(es_path, start_minute, end_minute)
    opra_bars, strike_trackers = build_opra_tape(
        opra_path, trade_date, start_minute, end_minute, trough_price, track_strikes
    )

    # Detect scare dips
    scare_dips = detect_scare_dips(es_bars, trough_minute, trough_price)

    # Bounce metrics
    bounce = compute_bounce_metrics(es_bars, trough_minute, trough_price, depth)

    # Volume climax detection
    volume_climax_minute = None
    volume_climax_ratio = 0.0
    for m in range(max(0, trough_minute - 5), min(trough_minute + 10, CLOSE_MINUTE)):
        if m in opra_bars and m in baseline and baseline[m] > 0:
            ratio = opra_bars[m].total_volume / baseline[m]
            if ratio > volume_climax_ratio:
                volume_climax_ratio = ratio
                volume_climax_minute = m

    profile = TapeProfile(
        date=date_str,
        label=label,
        trough_minute=trough_minute,
        trough_price=trough_price,
        close_price=close_price,
        depth_pts=depth,
        recovery_pts=recovery,
        latr_20=latr_20,
        es_bars=es_bars,
        opra_bars=opra_bars,
        strike_trackers=strike_trackers,
        scare_dips=scare_dips,
        bounce_velocity_5min=bounce.get("bounce_velocity_5min", 0.0),
        bounce_velocity_10min=bounce.get("bounce_velocity_10min", 0.0),
        time_to_50pct=bounce.get("time_to_50pct"),
        time_to_75pct=bounce.get("time_to_75pct"),
        time_to_100pct=bounce.get("time_to_100pct"),
        max_intra_recovery_drawdown=max((d.depth_pts for d in scare_dips), default=0.0),
        volume_climax_minute=volume_climax_minute,
        volume_climax_ratio=volume_climax_ratio,
    )
    return profile


def profile_to_json(profile: TapeProfile, baseline: dict[int, float]) -> dict:
    """Serialize a TapeProfile to JSON-friendly dict."""
    es_series = []
    for m in sorted(profile.es_bars):
        bar = profile.es_bars[m]
        if bar.trade_count == 0:
            continue
        ct_hour = 13 + m // 60
        ct_min = m % 60
        es_series.append({
            "minute": m,
            "time_ct": f"{ct_hour:02d}:{ct_min:02d}",
            "open": bar.open_p,
            "high": bar.high_p,
            "low": bar.low_p,
            "close": bar.close_p,
            "vwap": round(bar.vwap_p, 4),
            "trades": bar.trade_count,
            "volume": bar.total_size,
        })

    opra_series = []
    for m in sorted(profile.opra_bars):
        bar = profile.opra_bars[m]
        if bar.trade_count == 0:
            continue
        ct_hour = 13 + m // 60
        ct_min = m % 60
        expected = baseline.get(m, 0)
        ratio = bar.total_volume / expected if expected > 0 else 0
        opra_series.append({
            "minute": m,
            "time_ct": f"{ct_hour:02d}:{ct_min:02d}",
            "total_volume": bar.total_volume,
            "put_volume": bar.put_volume,
            "call_volume": bar.call_volume,
            "dte0_volume": bar.dte0_volume,
            "dte0_fraction": round(bar.dte0_fraction, 4),
            "pc_ratio": round(bar.pc_volume_ratio, 4) if bar.pc_volume_ratio != float('inf') else 99.0,
            "total_premium_usd": round(bar.total_premium, 2),
            "put_premium_usd": round(bar.put_premium, 2),
            "call_premium_usd": round(bar.call_premium, 2),
            "avg_trade_size": round(bar.avg_trade_size, 2),
            "large_trades": bar.large_trade_count,
            "expected_volume": expected,
            "volume_ratio": round(ratio, 4),
        })

    # Strike tracker series
    strike_series = {}
    for key, tracker in profile.strike_trackers.items():
        series = []
        for m in sorted(tracker.minute_prices):
            ct_hour = 13 + m // 60
            ct_min = m % 60
            last = tracker.last_price_at_minute(m)
            vwap = tracker.vwap_at_minute(m)
            vol = sum(s for _, s in tracker.minute_prices[m])
            series.append({
                "minute": m,
                "time_ct": f"{ct_hour:02d}:{ct_min:02d}",
                "last_price": last,
                "vwap_price": round(vwap, 4) if vwap else None,
                "volume": vol,
            })
        if series:
            strike_series[key] = series

    scare_dip_list = []
    for dip in profile.scare_dips:
        scare_dip_list.append({
            "start_minute": dip.start_minute,
            "start_price": dip.start_price,
            "low_minute": dip.low_minute,
            "low_price": dip.low_price,
            "end_minute": dip.end_minute,
            "depth_pts": round(dip.depth_pts, 2),
            "duration_minutes": dip.duration_minutes,
            "recovery_so_far_pts": round(dip.recovery_so_far_pts, 2),
            "depth_pct_of_recovery": round(dip.depth_pct_of_recovery, 2),
        })

    return {
        "date": profile.date,
        "label": profile.label,
        "trough_minute": profile.trough_minute,
        "trough_price": profile.trough_price,
        "close_price": profile.close_price,
        "depth_pts": round(profile.depth_pts, 2),
        "recovery_pts": round(profile.recovery_pts, 2),
        "latr_20": profile.latr_20,
        "bounce_metrics": {
            "velocity_5min_pts_per_min": round(profile.bounce_velocity_5min, 4),
            "velocity_10min_pts_per_min": round(profile.bounce_velocity_10min, 4),
            "time_to_50pct_min": profile.time_to_50pct,
            "time_to_75pct_min": profile.time_to_75pct,
            "time_to_100pct_min": profile.time_to_100pct,
            "max_intra_recovery_drawdown_pts": round(profile.max_intra_recovery_drawdown, 2),
        },
        "volume_climax": {
            "minute": profile.volume_climax_minute,
            "ratio": round(profile.volume_climax_ratio, 4),
        },
        "scare_dip_count": len(profile.scare_dips),
        "scare_dips": scare_dip_list,
        "es_1min": es_series,
        "opra_1min": opra_series,
        "strike_premiums": strike_series,
    }


def print_tape_summary(profile: TapeProfile, baseline: dict[int, float]):
    """Print a human-readable summary of the tape profile."""
    trough_m = profile.trough_minute
    ct_h = 13 + trough_m // 60
    ct_min = trough_m % 60

    print(f"\n{'='*72}")
    print(f"  TAPE PROFILE: {profile.date}  ({profile.label})")
    print(f"{'='*72}")
    print(f"  Trough: {ct_h:02d}:{ct_min:02d} CT @ {profile.trough_price:.2f}")
    print(f"  Close:  {profile.close_price:.2f}")
    print(f"  Depth:  {profile.depth_pts:.1f} pts  |  Recovery: {profile.recovery_pts:.1f} pts "
          f"({profile.recovery_pts/profile.depth_pts*100:.0f}%)" if profile.depth_pts > 0 else "")
    print(f"  LATR₂₀: {profile.latr_20:.1f}")
    print()

    # Bounce metrics
    print("  BOUNCE METRICS")
    print(f"    Velocity (5min):  {profile.bounce_velocity_5min:.2f} pts/min")
    print(f"    Velocity (10min): {profile.bounce_velocity_10min:.2f} pts/min")
    t50 = profile.time_to_50pct
    t75 = profile.time_to_75pct
    t100 = profile.time_to_100pct
    print(f"    Time to 50%: {t50} min" if t50 is not None else "    Time to 50%: never")
    print(f"    Time to 75%: {t75} min" if t75 is not None else "    Time to 75%: never")
    print(f"    Time to 100%: {t100} min" if t100 is not None else "    Time to 100%: never")
    print()

    # Volume climax
    if profile.volume_climax_minute is not None:
        vc_h = 13 + profile.volume_climax_minute // 60
        vc_min = profile.volume_climax_minute % 60
        offset = profile.volume_climax_minute - trough_m
        print(f"  VOLUME CLIMAX")
        print(f"    Peak at {vc_h:02d}:{vc_min:02d} CT (T{offset:+d}min), ratio {profile.volume_climax_ratio:.2f}x expected")
        print()

    # Scare dips
    print(f"  SCARE DIPS: {len(profile.scare_dips)}")
    for i, dip in enumerate(profile.scare_dips, 1):
        s_h = 13 + dip.start_minute // 60
        s_min = dip.start_minute % 60
        l_h = 13 + dip.low_minute // 60
        l_min = dip.low_minute % 60
        print(f"    #{i}: {s_h:02d}:{s_min:02d}→{l_h:02d}:{l_min:02d} "
              f"depth {dip.depth_pts:.1f}pts ({dip.depth_pct_of_recovery:.0f}% of recovery) "
              f"dur {dip.duration_minutes}min")
    print()

    # ES price trajectory (every 5 minutes)
    print("  ES PRICE TRAJECTORY (5-min intervals)")
    print(f"    {'Time':>5}  {'Close':>8}  {'Δ Trough':>9}  {'Range':>6}")
    sorted_mins = sorted(m for m in profile.es_bars if profile.es_bars[m].trade_count > 0)
    for m in sorted_mins:
        if m % 5 != 0 and m != trough_m and m != sorted_mins[-1]:
            continue
        bar = profile.es_bars[m]
        ct_h = 13 + m // 60
        ct_min = m % 60
        delta = bar.close_p - profile.trough_price
        rng = bar.high_p - bar.low_p
        marker = " ◄ TROUGH" if m == trough_m else ""
        print(f"    {ct_h:02d}:{ct_min:02d}  {bar.close_p:>8.2f}  {delta:>+9.2f}  {rng:>6.2f}{marker}")
    print()

    # OPRA volume trajectory (5-min intervals, time-normalized)
    print("  OPRA VOLUME (5-min intervals, time-normalized)")
    print(f"    {'Time':>5}  {'Volume':>8}  {'Ratio':>6}  {'0DTE%':>6}  {'P/C':>5}  {'Premium$':>10}")
    for m in sorted(profile.opra_bars):
        if m % 5 != 0 and m != trough_m:
            continue
        bar = profile.opra_bars[m]
        if bar.trade_count == 0:
            continue
        ct_h = 13 + m // 60
        ct_min = m % 60
        expected = baseline.get(m, 0)
        ratio = bar.total_volume / expected if expected > 0 else 0
        marker = " ◄ TROUGH" if m == trough_m else ""
        print(f"    {ct_h:02d}:{ct_min:02d}  {bar.total_volume:>8,}  {ratio:>6.2f}x  "
              f"{bar.dte0_fraction*100:>5.1f}%  {bar.pc_volume_ratio:>5.2f}  "
              f"${bar.total_premium:>10,.0f}{marker}")
    print()

    # Strike premium tracking
    if profile.strike_trackers:
        print("  STRIKE PREMIUM TRACKING (0DTE, select strikes)")
        for key, tracker in sorted(profile.strike_trackers.items()):
            if not tracker.minute_prices:
                continue
            sorted_track_mins = sorted(tracker.minute_prices.keys())
            first_m = sorted_track_mins[0]
            last_m = sorted_track_mins[-1]
            first_price = tracker.last_price_at_minute(first_m)
            last_price = tracker.last_price_at_minute(last_m)
            if first_price and last_price:
                mult = last_price / first_price if first_price > 0 else 0
                print(f"    {key}: ${first_price:.2f} → ${last_price:.2f} ({mult:.1f}x) "
                      f"over {len(sorted_track_mins)} minutes with trades")
        print()


def main():
    parser = argparse.ArgumentParser(description="Tape Reconstruction for post-entry study")
    parser.add_argument("--date", help="Single date to process (YYYY-MM-DD)")
    parser.add_argument("--all-v-days", action="store_true", help="Process all 13 V-days")
    parser.add_argument("--neg-a", action="store_true", help="Also process Neg-A continuation days")
    parser.add_argument("--json", action="store_true", help="Output JSON profiles")
    parser.add_argument("--quiet", action="store_true", help="Suppress summary output")
    args = parser.parse_args()

    if not args.date and not args.all_v_days:
        args.date = "2026-05-21"
        print("No date specified, defaulting to May 21 anchor case.", file=sys.stderr)

    # Load v_days data
    with open(MEASUREMENT_DIR / "v_days.jsonl") as f:
        all_days = {d["date"]: d for d in (json.loads(l) for l in f)}

    baseline = load_volume_baseline()

    # Determine which days to process
    dates_to_process = []
    if args.date:
        dates_to_process = [args.date]
    elif args.all_v_days:
        dates_to_process = CONFIRMED_V_DAYS[:]

    if args.neg_a:
        for date_str, info in all_days.items():
            v_down = info.get("v_down", {})
            criteria = v_down.get("criteria", {})
            if (date_str not in CONFIRMED_V_DAYS
                    and criteria.get("depth_ok") is True
                    and criteria.get("recovery_ok") is False):
                dates_to_process.append(date_str)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    profiles = []
    for date_str in dates_to_process:
        if date_str not in all_days:
            print(f"  SKIP {date_str}: not in v_days.jsonl", file=sys.stderr)
            continue

        day_info = all_days[date_str]
        profile = build_tape_profile(day_info, baseline)
        if profile is None:
            continue

        profiles.append(profile)

        if not args.quiet:
            print_tape_summary(profile, baseline)

        if args.json:
            out_path = OUTPUT_DIR / f"tape_{date_str}.json"
            with open(out_path, "w") as f:
                json.dump(profile_to_json(profile, baseline), f, indent=2)
            print(f"  Wrote {out_path}", file=sys.stderr)

    # Summary across all processed days
    if len(profiles) > 1 and not args.quiet:
        print(f"\n{'='*72}")
        print(f"  CROSS-DAY SUMMARY ({len(profiles)} days)")
        print(f"{'='*72}")
        print(f"  {'Date':>10}  {'Depth':>6}  {'Rec%':>5}  {'V5':>5}  {'T50%':>5}  "
              f"{'Dips':>4}  {'MaxDip':>6}  {'VolClx':>6}")
        for p in profiles:
            rec_pct = p.recovery_pts / p.depth_pts * 100 if p.depth_pts > 0 else 0
            t50 = f"{p.time_to_50pct:>5}" if p.time_to_50pct is not None else "  n/a"
            print(f"  {p.date:>10}  {p.depth_pts:>6.1f}  {rec_pct:>4.0f}%  "
                  f"{p.bounce_velocity_5min:>5.2f}  {t50}  "
                  f"{len(p.scare_dips):>4}  {p.max_intra_recovery_drawdown:>6.1f}  "
                  f"{p.volume_climax_ratio:>6.2f}x")


if __name__ == "__main__":
    main()
