#!/usr/bin/env python3
"""Calibrate 'meaningful spike' thresholds for the GexBot orderflow oflow metrics.

Freddy's qualifier -- "meaningful versus prior spikes" -- has never had a number
behind it; live reads used an ad-hoc 100MM line (st-pz3r).  This script computes
the actual distributions so a magnitude adjective can cite a percentile instead
of a guess.

Two cadences exist in the corpus and they are NOT interchangeable:

  * ``gexbot_orderflow_1s.jsonl``  -- the 1 Hz poller (2026-08-10 onward).  Near
    the vendor's own ~1.3s snap rate, so it sees nearly every value the vendor
    publishes.
  * ``gexbot.jsonl``              -- the original ~60-80s poller.  Same vendor
    field, but we only observe roughly one in sixty of the vendor's snapshots,
    so transient peaks are missed and the upper tail is biased low.

Pooling the two would silently mix a well-sampled tail with an undersampled one.
Instead the 1 Hz days are the primary calibration, the 60s days are a regime
cross-check, and the undersampling bias is measured directly by decimating a
1 Hz day down to 60s and re-running the same percentiles.

Vendor snapshots are deduplicated on the vendor ``timestamp`` field: polling
faster than the vendor publishes yields repeated identical rows, and counting
them would put artificial mass wherever the feed happened to stall.

Usage::

    python3 scripts/calibrate_oflow_thresholds.py                  # default corpus
    python3 scripts/calibrate_oflow_thresholds.py --out docs/measurement/x.md
    python3 scripts/calibrate_oflow_thresholds.py --json           # machine-readable
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence

LOG = logging.getLogger("calibrate_oflow")

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "data" / "corpus"

# The six orderflow-rate fields.  "z"/zero-DTE and "one"/one-DTE are separate
# surfaces with separate scales -- never pool them.
METRICS = (
    "dexoflow",
    "gexoflow",
    "cvroflow",
    "one_dexoflow",
    "one_gexoflow",
    "one_cvroflow",
)

# Reported percentiles.  p50 anchors "ordinary", p99 anchors "rare"; the ones in
# between are what an adjective should actually cite.
PERCENTILES = (50.0, 75.0, 90.0, 95.0, 99.0, 99.9)

# Regular trading hours in US/Central, the units Steve's screen uses.
RTH_START_CT = (8, 30)
RTH_END_CT = (15, 0)
CT_OFFSET = timedelta(hours=-5)  # CDT; the corpus dates are all summer-time

ORDERFLOW_ENDPOINT = "/SPX/orderflow/orderflow"


class CalibrationError(RuntimeError):
    """Raised when the corpus cannot support a calibration."""


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def _parse_utc(stamp: str) -> datetime | None:
    """Parse an ISO-8601 Zulu stamp; return None rather than raising on junk."""
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _ct_hour(when: datetime) -> int:
    return (when + CT_OFFSET).hour


def _in_rth(when: datetime) -> bool:
    """True only inside a weekday RTH window.

    The weekday test is not redundant with the clock test: the collector keeps
    polling over the weekend, and the vendor simply republishes Friday's closing
    state. Those rows carry real-looking oflow values that would land in the
    distribution as ordinary observations. Deduplication happens to collapse them
    today because the vendor timestamp is frozen, but that is a side effect, not
    a guarantee -- one weekend snapshot with a nudged timestamp would poison the
    percentiles silently.
    """
    local = when + CT_OFFSET
    if local.weekday() >= 5:  # Saturday, Sunday
        return False
    start = local.replace(hour=RTH_START_CT[0], minute=RTH_START_CT[1], second=0, microsecond=0)
    end = local.replace(hour=RTH_END_CT[0], minute=RTH_END_CT[1], second=0, microsecond=0)
    # Half-open: the poller stops at exactly 15:00:00, and including that one
    # boundary snapshot spawns a 15:00 hour bucket holding a single observation,
    # which then prints alongside buckets of 2,500 as though comparable.
    return start <= local < end


def _iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield parsed rows, tolerating a truncated final line on a live file."""
    bad = 0
    with path.open() as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                # A live poller can be mid-write on the last line; anything more
                # than that is corruption worth shouting about.
                LOG.debug("%s:%d unparseable", path.name, lineno)
    if bad > 1:
        LOG.warning("%s: skipped %d unparseable lines", path.name, bad)


def load_1s(path: Path) -> list[dict]:
    """Load a 1 Hz orderflow file into flat snapshot dicts."""
    rows: list[dict] = []
    for raw in _iter_jsonl(path):
        when = _parse_utc(raw.get("ts_pull_utc", ""))
        if when is None:
            continue
        rows.append({"when": when, "vendor_ts": raw.get("timestamp"), "values": raw})
    return rows


def load_60s(path: Path) -> list[dict]:
    """Load a ~60s poller file, digging the orderflow payload out of the envelope."""
    rows: list[dict] = []
    for raw in _iter_jsonl(path):
        when = _parse_utc(raw.get("ts_pull_utc", ""))
        if when is None:
            continue
        payload = (raw.get("data") or {}).get("responses", {}).get(ORDERFLOW_ENDPOINT)
        if not isinstance(payload, dict):
            continue
        rows.append({"when": when, "vendor_ts": payload.get("timestamp"), "values": payload})
    return rows


def dedupe_vendor(rows: Sequence[dict]) -> list[dict]:
    """Drop consecutive rows carrying the same vendor timestamp.

    Polling at 1 Hz against a ~1.3s publisher means roughly a quarter of rows are
    re-reads of a snapshot already counted.  Leaving them in would weight the
    distribution toward whatever value the feed happened to sit on.
    """
    kept: list[dict] = []
    last = object()
    for row in rows:
        ts = row.get("vendor_ts")
        if ts is not None and ts == last:
            continue
        last = ts
        kept.append(row)
    return kept


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------


def percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile over a pre-sorted sequence."""
    if not sorted_values:
        return math.nan
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[int(rank)]
    weight = rank - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def distribution(values: Iterable[float]) -> dict:
    """Absolute-value distribution summary for one metric."""
    magnitudes = sorted(abs(v) for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    if not magnitudes:
        return {"n": 0}
    return {
        "n": len(magnitudes),
        "max": magnitudes[-1],
        **{f"p{pct:g}": percentile(magnitudes, pct) for pct in PERCENTILES},
    }


def profile(rows: Sequence[dict], rth_only: bool = True) -> dict:
    """Per-metric distributions overall, plus a by-CT-hour breakdown."""
    scoped = [r for r in rows if not rth_only or _in_rth(r["when"])]
    overall = {m: distribution(r["values"].get(m) for r in scoped) for m in METRICS}

    by_hour: dict[str, dict] = {}
    buckets: dict[int, list[dict]] = defaultdict(list)
    for row in scoped:
        buckets[_ct_hour(row["when"])].append(row)
    for hour in sorted(buckets):
        by_hour[f"{hour:02d}"] = {
            m: distribution(r["values"].get(m) for r in buckets[hour]) for m in METRICS
        }

    return {"n_snapshots": len(scoped), "overall": overall, "by_ct_hour": by_hour}


def decimate(rows: Sequence[dict], every_seconds: int = 60, offset: int = 0) -> list[dict]:
    """Keep one row per `every_seconds` window -- simulates the old 60s poller.

    Buckets are anchored to the absolute clock, shifted by `offset`, rather than
    chained from the previous kept row. Chaining looks equivalent and is not:
    the 1 Hz feed has multi-second gaps, and a single gap wider than the offset
    resynchronises every downstream pick, so all phases collapse onto the same
    sample set and a phase sweep silently measures nothing.
    """
    kept: list[dict] = []
    last_bucket: int | None = None
    for row in rows:
        bucket = (int(row["when"].timestamp()) - offset) // every_seconds
        if bucket != last_bucket:
            kept.append(row)
            last_bucket = bucket
    return kept


def feed_gaps(rows: Sequence[dict], threshold_s: int = 5) -> dict:
    """Characterise holes in the 1 Hz feed.

    Coverage is part of instrument adequacy: a percentile computed over a series
    with unnoticed holes describes the hours that were recorded, not the session.
    """
    gaps: list[tuple[datetime, float]] = []
    for prev, cur in zip(rows, rows[1:]):
        delta = (cur["when"] - prev["when"]).total_seconds()
        if delta > threshold_s:
            gaps.append((prev["when"], delta))
    total_span = (rows[-1]["when"] - rows[0]["when"]).total_seconds() if len(rows) > 1 else 0
    missing = sum(d for _, d in gaps)
    return {
        "n_gaps": len(gaps),
        "worst_s": max((d for _, d in gaps), default=0.0),
        "total_missing_s": missing,
        "span_s": total_span,
        "coverage_pct": (1 - missing / total_span) * 100 if total_span else 100.0,
        "worst_at": max(gaps, key=lambda g: g[1])[0].isoformat() if gaps else None,
    }


def sampling_spread(rows: Sequence[dict], every_seconds: int = 60,
                    phases: int = 20) -> dict:
    """How much a 60s poller's answer depends on *when* in the minute it polled.

    A subsample's percentile is an unbiased but noisy estimate of the full
    population's -- it is not systematically low, which is why the honest
    question is not "how much does 60s undershoot" but "how far apart do two
    equally valid 60s pollers land". Decimating at many phase offsets answers
    that directly: the spread is the resolution the old cadence never had.
    """
    if not rows:
        return {}
    step = max(1, every_seconds // phases)
    estimates: dict[str, dict[str, list[float]]] = {
        m: {f"p{p:g}": [] for p in PERCENTILES} for m in METRICS
    }
    n_samples: list[int] = []
    for offset in range(0, every_seconds, step):
        sub = decimate(rows, every_seconds, offset)
        n_samples.append(len(sub))
        for metric in METRICS:
            stats = distribution(r["values"].get(metric) for r in sub)
            for key in estimates[metric]:
                if key in stats:
                    estimates[metric][key].append(stats[key])

    full = {m: distribution(r["values"].get(m) for r in rows) for m in METRICS}
    spread: dict[str, dict] = {}
    for metric in METRICS:
        if not full[metric].get("n"):
            continue
        per_pct = {}
        for key, values in estimates[metric].items():
            if not values:
                continue
            values = sorted(values)
            truth = full[metric].get(key)
            per_pct[key] = {
                "truth": truth,
                "lo": values[0],
                "hi": values[-1],
                # Worst miss any single 60s poller would have reported, as a
                # fraction of the true value.
                "worst_err_pct": max(abs(v - truth) / truth * 100 for v in values)
                if truth else math.nan,
            }
        spread[metric] = per_pct

    return {
        "phases": len(n_samples),
        "n_full": len(rows),
        "n_per_phase": round(sum(n_samples) / len(n_samples)) if n_samples else 0,
        "per_metric": spread,
    }


def redundancy(rows: Sequence[dict]) -> list[dict]:
    """Pearson correlation between every metric pair.

    Reported because two fields that move as mirrors are one fact, not two: a
    read that cites both as confirming evidence is double-counting a single
    observation.
    """
    series: dict[str, list[float]] = {}
    for metric in METRICS:
        vals = [r["values"].get(metric) for r in rows]
        if all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals) and vals:
            series[metric] = vals

    pairs: list[dict] = []
    names = list(series)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            xs, ys = series[a], series[b]
            n = len(xs)
            mx, my = sum(xs) / n, sum(ys) / n
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
            sy = math.sqrt(sum((y - my) ** 2 for y in ys))
            if sx == 0 or sy == 0:
                continue
            pairs.append({"a": a, "b": b, "r": cov / (sx * sy)})
    pairs.sort(key=lambda p: -abs(p["r"]))
    return pairs


# --------------------------------------------------------------------------
# threshold selection
# --------------------------------------------------------------------------


def choose_thresholds(primary: dict) -> dict:
    """Turn the 1 Hz distribution into the three adjectives a read may use.

    The mapping is deliberately blunt -- an adjective earns its place by naming
    the percentile it cites, not by sounding dramatic:

      elevated    p90  -- top tenth of the session; worth noticing, not acting
      notable     p95  -- top twentieth
      extreme     p99  -- top hundredth; the only tier that merits "spike"
    """
    tiers = {"elevated": "p90", "notable": "p95", "extreme": "p99"}
    chosen: dict[str, dict] = {}
    for metric in METRICS:
        stats = primary["overall"].get(metric, {})
        if not stats.get("n"):
            continue
        chosen[metric] = {
            "n": stats["n"],
            "median_abs": stats["p50"],
            **{tier: stats[key] for tier, key in tiers.items()},
        }
    return chosen


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def _fmt(value: float) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "--"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.2f}"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_markdown(result: dict) -> str:
    primary = result["primary"]
    out: list[str] = []
    add = out.append

    add("---")
    add("type: measurement")
    add("title: Orderflow spike thresholds — calibrated from the 1 Hz archive")
    add("description: Per-metric absolute-value percentiles for the six GexBot "
        "oflow fields, replacing the ad-hoc 100MM line with cited numbers.")
    add(f"timestamp: {result['generated_utc']}")
    add("bead: st-pz3r")
    add("---")
    add("")
    add("# Orderflow Spike Thresholds")
    add("")
    add("## What this replaces")
    add("")
    add("Live reads had been calling an oflow move \"meaningful\" against an "
        "ad-hoc 100MM line that nobody measured. These are the measured "
        "distributions. An adjective in a read now cites a percentile or it "
        "does not get used.")
    add("")

    add("## Sampling — why only the 1 Hz days calibrate")
    add("")
    add(f"**Primary (1 Hz):** {', '.join(result['primary_days'])} — "
        f"{primary['n_snapshots']:,} distinct vendor snapshots inside RTH "
        f"(08:30–15:00 CT) after deduplicating repeated vendor timestamps.")
    add("")
    if result["cross_check_days"]:
        add(f"**Cross-check (~60s):** {', '.join(result['cross_check_days'])} — "
            "same vendor field, but roughly one snapshot in sixty is observed. "
            "Used only to ask whether the 1 Hz days were a typical regime, "
            "never pooled into the thresholds.")
        add("")

    gaps = result.get("feed_gaps")
    if gaps and gaps.get("n_gaps"):
        add("### Feed coverage")
        add("")
        add(f"The 1 Hz feed has **{gaps['n_gaps']} gaps** wider than 5 seconds "
            f"across the calibration session, {gaps['total_missing_s']:.0f}s "
            f"missing in total — **{gaps['coverage_pct']:.1f}% coverage**. "
            f"The worst is {gaps['worst_s']:.0f}s at {gaps['worst_at']}. "
            "Small enough not to move the percentiles, but it is the reason "
            "the phase sweep below is anchored to the wall clock rather than "
            "chained from the previous sample: one gap wider than the offset "
            "resynchronises every downstream pick, and a chained sweep would "
            "have reported near-zero spread while actually measuring nothing.")
        add("")

    spread = result.get("sampling_spread")
    if spread and spread.get("per_metric"):
        add("### What the old 60s cadence could not have told us")
        add("")
        add("A subsample's percentile is a *noisy* estimate of the full "
            "population's, not a systematically low one — so the useful "
            "question is not how far 60s undershoots, but how far apart two "
            "equally legitimate 60s pollers land. The 1 Hz day was decimated "
            f"at {spread['phases']} different phase offsets "
            f"(~{spread['n_per_phase']:,} snapshots each, against "
            f"{spread['n_full']:,} at 1 Hz) and the same percentiles recomputed. "
            "The range is the answer:")
        add("")
        rows = []
        for metric in METRICS:
            per = spread["per_metric"].get(metric)
            if not per:
                continue
            cells = [metric]
            for key in ("p95", "p99"):
                stat = per.get(key)
                if not stat:
                    cells += ["--", "--"]
                    continue
                cells.append(_fmt(stat["truth"]))
                cells.append(f"{_fmt(stat['lo'])} – {_fmt(stat['hi'])}"
                             f" ({stat['worst_err_pct']:.0f}% off)")
            rows.append(cells)
        add(_table(["metric", "p95 (1 Hz)", "p95 range across 60s phases",
                    "p99 (1 Hz)", "p99 range across 60s phases"], rows))
        add("")
        add("Read the right-hand columns as error bars on every number the "
            "old poller ever produced. A threshold that moves by tens of "
            "percent depending on which second of the minute you sampled is "
            "not a threshold — which is why only the 1 Hz archive calibrates.")
        add("")

    pairs = result.get("redundancy") or []
    strong = [p for p in pairs if abs(p["r"]) >= 0.9]
    if strong:
        add("## These are not six independent metrics")
        add("")
        add("Pearson correlation over the calibration day, pairs at |r| ≥ 0.90:")
        add("")
        add(_table(["pair", "r"],
                   [[f"{p['a']} vs {p['b']}", f"{p['r']:+.4f}"] for p in strong]))
        add("")
        add("**Consequence for reads:** a mirrored pair carries one "
            "observation, not two. Citing both as if they corroborate each "
            "other inflates confidence in exactly the situation where it "
            "should not move. Pick one of each pair as the reported metric and "
            "treat the other as a consistency check — if a mirrored pair ever "
            "stops mirroring, *that* divergence is the finding.")
        add("")

    add("## Thresholds")
    add("")
    add("Absolute value. Zero-DTE and one-DTE surfaces are kept separate "
        "because their scales differ by roughly two orders of magnitude.")
    add("")
    rows = []
    for metric, t in result["thresholds"].items():
        rows.append([metric, f"{t['n']:,}", _fmt(t["median_abs"]),
                     _fmt(t["elevated"]), _fmt(t["notable"]), _fmt(t["extreme"])])
    add(_table(["metric", "n", "median abs", "elevated (p90)",
                "notable (p95)", "extreme (p99)"], rows))
    add("")
    add("Only **extreme** earns the word *spike*. *Elevated* and *notable* are "
        "context, not signal.")
    add("")
    add("These whole-day numbers are the fallback. Where an hourly bucket "
        "exists, the hourly threshold below is the one to cite — see the next "
        "section for why the difference is large enough to matter.")
    add("")

    add("## By session hour (CT) — the operative thresholds")
    add("")
    add("Magnitude is strongly non-stationary: the same number that is "
        "unremarkable at 14:00 is far out in the tail at 09:00. A single "
        "whole-day threshold therefore under-flags the morning and over-flags "
        "the last hour. p95 of the absolute value, by hour:")
    add("")
    hours = sorted(primary["by_ct_hour"])
    rows = []
    for metric in METRICS:
        cells = [metric]
        for hour in hours:
            stats = primary["by_ct_hour"][hour].get(metric, {})
            cells.append(_fmt(stats.get("p95")) if stats.get("n") else "--")
        rows.append(cells)
    add(_table(["metric"] + [f"{h}:00" for h in hours], rows))
    add("")
    counts = [f"{h}:00 n={primary['by_ct_hour'][h][METRICS[0]].get('n', 0):,}" for h in hours]
    add("Snapshots per hour: " + ", ".join(counts) + ".")
    add("")

    if result.get("regime_check"):
        add("## Regime check — was the calibration day typical?")
        add("")
        add("The 1 Hz day decimated to 60s, compared against the genuine 60s "
            "days at the same cadence. Like-for-like sampling, so a large gap "
            "means the regime differed, not the instrument:")
        add("")
        rows = []
        for day, prof in result["regime_check"].items():
            for metric in ("gexoflow", "cvroflow", "dexoflow"):
                stats = prof["overall"].get(metric, {})
                rows.append([day, metric, f"{stats.get('n', 0):,}",
                             _fmt(stats.get("p95")), _fmt(stats.get("p99"))])
        add(_table(["day", "metric", "n", "p95", "p99"], rows))
        add("")

    add("## Known limits")
    add("")
    for limit in result["limits"]:
        add(f"- {limit}")
    add("")

    return "\n".join(out)


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------


def discover_days() -> tuple[list[Path], list[Path]]:
    """Split the corpus into 1 Hz files and 60s-only files."""
    one_hz: list[Path] = []
    sixty: list[Path] = []
    if not CORPUS.is_dir():
        raise CalibrationError(f"corpus directory not found: {CORPUS}")
    for day in sorted(CORPUS.iterdir()):
        if not day.is_dir():
            continue
        fast = day / "gexbot_orderflow_1s.jsonl"
        slow = day / "gexbot.jsonl"
        if fast.is_file() and fast.stat().st_size > 0:
            one_hz.append(fast)
        elif slow.is_file() and slow.stat().st_size > 0:
            sixty.append(slow)
    return one_hz, sixty


def run(exclude_today: str | None = None) -> dict:
    one_hz_paths, sixty_paths = discover_days()
    if exclude_today:
        one_hz_paths = [p for p in one_hz_paths if p.parent.name != exclude_today]

    if not one_hz_paths:
        raise CalibrationError(
            "no 1 Hz orderflow archive found — thresholds cannot be calibrated from "
            "the 60s poller alone, since it undersamples the tail this measures"
        )

    primary_rows: list[dict] = []
    for path in one_hz_paths:
        rows = dedupe_vendor(load_1s(path))
        LOG.info("1Hz %s: %d distinct vendor snapshots", path.parent.name, len(rows))
        primary_rows.extend(rows)
    primary_rows.sort(key=lambda r: r["when"])

    primary = profile(primary_rows)
    if not primary["n_snapshots"]:
        raise CalibrationError("1 Hz archive contains no RTH snapshots")

    rth_rows = [r for r in primary_rows if _in_rth(r["when"])]
    decimated_rows = decimate(rth_rows, 60)
    spread = sampling_spread(rth_rows)
    pairs = redundancy(rth_rows)
    gaps = feed_gaps(rth_rows)

    # Regime cross-check at matched cadence.
    regime: dict[str, dict] = {}
    for path in sixty_paths:
        rows = dedupe_vendor(load_60s(path))
        prof = profile(rows)
        if prof["n_snapshots"]:
            regime[path.parent.name] = prof
            LOG.info("60s %s: %d RTH snapshots", path.parent.name, prof["n_snapshots"])
    if decimated_rows:
        regime[f"{one_hz_paths[0].parent.name}+ (1Hz→60s)"] = profile(decimated_rows)

    limits = [
        f"Calibrated on {len(one_hz_paths)} day(s) of 1 Hz data "
        f"({', '.join(p.parent.name for p in one_hz_paths)}). One or two sessions "
        "is a thin base for a p99 — re-run as the archive grows and expect the "
        "extreme tier to move.",
        "Percentiles are of the absolute value, so a threshold says a move was "
        "large, not which direction it favoured.",
        "The vendor publishes at roughly 1.3s; polling at 1 Hz still misses "
        "nothing observable, but repeated timestamps are deduplicated, so n is "
        "below the raw row count.",
        "Session-hour buckets thin out at the edges — treat an hour with a few "
        "hundred snapshots as indicative only.",
    ]
    if exclude_today:
        limits.append(
            f"Today ({exclude_today}) was excluded: a partial session would weight "
            "the distribution toward whichever hours have elapsed."
        )

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "primary_days": [p.parent.name for p in one_hz_paths],
        "cross_check_days": [p.parent.name for p in sixty_paths],
        "primary": primary,
        "feed_gaps": gaps,
        "sampling_spread": spread,
        "redundancy": pairs,
        "regime_check": regime,
        "thresholds": choose_thresholds(primary),
        "limits": limits,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    parser.add_argument("--json", action="store_true", help="emit raw JSON to stdout")
    parser.add_argument("--exclude-day", help="corpus day to omit, e.g. a partial session")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    try:
        result = run(exclude_today=args.exclude_day)
    except CalibrationError as exc:
        LOG.error("%s", exc)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    report = render_markdown(result)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report)
        LOG.info("wrote %s", args.out)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
