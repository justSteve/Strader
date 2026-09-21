#!/usr/bin/env python3
"""Absorption read rate over the recorded MBP-1 days, at production floors. [co-qp8cn]

Phase 1 of Desk's 2026-09-20 work order: before the absorption cue is wired to
the live footprint page, measure what the tracker would have emitted on the
days already captured. The floors in ``market/signals/orderflow_config.py``
were calibrated on one holiday-eve session (2026-07-02) against a 10-40 reads
per session rarity band; this script says whether ordinary sessions land there.

Source is the raw ``.dbn.zst`` archive, not the day's JSONL — the live
collector writes the trade columns as null on every book row, so the JSONL
cannot drive the tracker (see ``market/orderflow/quotes.py``).

Method. ``AbsorptionTracker`` is run verbatim. Its two emission floors only
gate ``_close`` — they never touch episode dynamics — so each day is run once
with the floors lowered to a collection level, and the production count and
the candidate-floor grid are both read off that one population.
``tests/scripts/test_absorption_rate_survey.py`` pins that equivalence against
a verbatim production run. The tracker is restarted at every raw segment: a
segment boundary is a reconnect, and on a roll day the contract changes there.

Per day it reports, for the RTH session (08:30-15:00 CT) and the full capture:
read count, aggressive_vol and refill_events distributions, reads per CT hour,
the share inside the last ten minutes of RTH, and the emission grid.

Usage:
    .venv/bin/python scripts/measurement/absorption_rate_survey.py
    .venv/bin/python scripts/measurement/absorption_rate_survey.py --from 2026-09-01 --to 2026-09-18
    .venv/bin/python scripts/measurement/absorption_rate_survey.py --date 2026-09-18 --jobs 1

Writes one JSON row per day to ``data/measurement/absorption-rate-survey.jsonl``
(``--out``), replacing any earlier row for the same day, and prints the table.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date as _date, time as _time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import market.orderflow.absorption as _abs  # noqa: E402
from market.orderflow.absorption import AbsorptionTracker  # noqa: E402
from market.orderflow.quotes import mbp1_raw_segments, read_mbp1_raw_segment  # noqa: E402
from market.signals import orderflow_config as _cfg  # noqa: E402

logger = logging.getLogger("absorption_rate_survey")

CORPUS_ROOT = REPO / "data" / "corpus"
DEFAULT_OUT = REPO / "data" / "measurement" / "absorption-rate-survey.jsonl"

RTH_OPEN = _time(8, 30)
RTH_CLOSE = _time(15, 0)
LAST_TEN = _time(14, 50)

# The production floors, read once before the module copies are lowered.
PROD_VOL_MIN = _cfg.ABSORPTION_VOL_MIN
PROD_REFILL_MIN = _cfg.ABSORPTION_REFILL_MIN

COLLECT_VOL_MIN = 50
VOL_CANDIDATES = (100, 200, 300, 500, 750, 1_000, 1_500)
REFILL_CANDIDATES = (1, 2, 3, 4, 6)


def pct(sorted_vals: list[int], q: float) -> int:
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def dist(vals: list[int]) -> dict:
    s = sorted(vals)
    return {"p50": pct(s, .50), "p75": pct(s, .75), "p90": pct(s, .90),
            "max": s[-1] if s else 0}


def in_rth(ts) -> bool:
    return RTH_OPEN <= ts.time() < RTH_CLOSE


def collect_episodes(streams) -> tuple[list, dict]:
    """Run the tracker over each (label, events) stream; return (episodes, facts).

    Episodes are AbsorptionReads emitted with the floors lowered to
    (COLLECT_VOL_MIN, 0). A read closed by ``flush`` — the segment ended while
    the level was still defended — is marked, since live it would have closed
    later and possibly larger.

    A segment that stops decoding part-way (the collector's connection dropped
    mid-record: 09-08 and 09-17 each hold one) keeps every event read before
    the break and is named in ``facts["unreadable"]``; the day is still counted.
    A segment that starts before the previous one ended is named in
    ``facts["overlapping"]`` — that day's counts include the same tape twice.
    """
    _abs.ABSORPTION_VOL_MIN = COLLECT_VOL_MIN
    _abs.ABSORPTION_REFILL_MIN = 0
    episodes: list[tuple] = []   # (read, flushed)
    facts = {"book_events": 0, "trade_events": 0, "trade_volume": 0,
             "rth_trade_volume": 0, "symbols": [], "first_ts": None, "last_ts": None,
             "unreadable": [], "overlapping": []}
    prev_end = None
    try:
        for label, events in streams:
            tracker = AbsorptionTracker()
            last = None
            seen = 0
            try:
                for e in events:
                    seen += 1
                    if seen == 1 and prev_end is not None and e.ts < prev_end:
                        # two collectors at once, or a replayed span: the same
                        # tape would be counted twice, so the day is flagged
                        facts["overlapping"].append({
                            "segment": label, "starts": e.ts.isoformat(),
                            "previous_ended": prev_end.isoformat()})
                    if facts["first_ts"] is None:
                        facts["first_ts"] = e.ts.isoformat()
                    if e.symbol and e.symbol not in facts["symbols"]:
                        facts["symbols"].append(e.symbol)
                    if e.action == "T" and e.size:
                        facts["trade_events"] += 1
                        facts["trade_volume"] += e.size
                        if in_rth(e.ts):
                            facts["rth_trade_volume"] += e.size
                    episodes.extend((r, False) for r in tracker.process(e))
                    last = e
            except Exception as exc:
                logger.warning("%s unreadable after %d events: %s", label, seen, exc)
                facts["unreadable"].append({
                    "segment": label, "events_before": seen,
                    "last_good_ts": last.ts.isoformat() if last else None,
                    "error": f"{type(exc).__name__}: {exc}"})
            facts["book_events"] += seen
            episodes.extend((r, True) for r in tracker.flush())
            if last is not None:
                facts["last_ts"] = last.ts.isoformat()
                prev_end = last.ts if prev_end is None else max(prev_end, last.ts)
    finally:
        _abs.ABSORPTION_VOL_MIN = PROD_VOL_MIN
        _abs.ABSORPTION_REFILL_MIN = PROD_REFILL_MIN
    return episodes, facts


def at_floors(episodes: list[tuple], vol_min: int, refill_min: int) -> list[tuple]:
    return [(r, f) for r, f in episodes
            if r.aggressive_vol >= vol_min and r.refill_events >= refill_min]


def overlap_reaches_rth(overlapping: list[dict]) -> bool:
    """True when a doubled span touches 08:30-15:00 CT — only then is the RTH
    count itself inflated (08-28 and 09-08 overlap overnight only)."""
    from datetime import datetime
    for o in overlapping:
        a = datetime.fromisoformat(o["starts"]).time()
        b = datetime.fromisoformat(o["previous_ended"]).time()
        if a < RTH_CLOSE and b >= RTH_OPEN:
            return True
    return False


def summarize(day: _date, segments: list[Path], episodes: list[tuple], facts: dict) -> dict:
    prod = at_floors(episodes, PROD_VOL_MIN, PROD_REFILL_MIN)
    rth = [(r, f) for r, f in prod if in_rth(r.timestamp)]
    by_hour: dict[str, int] = {}
    for r, _ in prod:
        key = f"{r.timestamp.hour:02d}"
        by_hour[key] = by_hour.get(key, 0) + 1
    rth_episodes = [(r, f) for r, f in episodes if in_rth(r.timestamp)]
    grid = {
        str(v): {str(k): len(at_floors(rth_episodes, v, k)) for k in REFILL_CANDIDATES}
        for v in VOL_CANDIDATES
    }
    # the same grid without the last ten minutes, where half the reads fall —
    # a floor chosen on the whole session is mostly a floor chosen on the close
    early = [(r, f) for r, f in rth_episodes if r.timestamp.time() < LAST_TEN]
    grid_early = {
        str(v): {str(k): len(at_floors(early, v, k)) for k in REFILL_CANDIDATES}
        for v in VOL_CANDIDATES
    }
    return {
        "date": day.isoformat(),
        "floors": {"vol_min": PROD_VOL_MIN, "refill_min": PROD_REFILL_MIN,
                   "band_ticks": _cfg.ABSORPTION_BAND_TICKS,
                   "depletion_min": _cfg.REFILL_DEPLETION_MIN,
                   "recovery_min": _cfg.REFILL_RECOVERY_MIN},
        "segments": len(segments),
        **facts,
        "overlap_reaches_rth": overlap_reaches_rth(facts.get("overlapping", [])),
        "episodes_collected": len(episodes),
        "reads_all": len(prod),
        "reads_rth": len(rth),
        "reads_rth_last_ten_min": sum(1 for r, _ in rth if r.timestamp.time() >= LAST_TEN),
        "reads_rth_flush_closed": sum(1 for _, f in rth if f),
        "reads_rth_bid": sum(1 for r, _ in rth if r.side == "bid"),
        "reads_rth_ask": sum(1 for r, _ in rth if r.side == "ask"),
        "reads_rth_broke": sum(1 for r, _ in rth if r.displacement_ticks < 0),
        "rth_aggressive_vol": dist([r.aggressive_vol for r, _ in rth]),
        "rth_refill_events": dist([r.refill_events for r, _ in rth]),
        "reads_by_hour_ct": dict(sorted(by_hour.items())),
        "rth_grid": grid,
        "rth_grid_before_1450": grid_early,
    }


def survey_day(day_iso: str) -> dict:
    day = _date.fromisoformat(day_iso)
    segments = mbp1_raw_segments(day)
    if not segments:
        return {"date": day_iso, "error": "no raw MBP-1 segments"}
    try:
        episodes, facts = collect_episodes(
            (seg.name, read_mbp1_raw_segment(seg)) for seg in segments)
    except Exception as e:  # one bad day must not sink the survey
        logger.exception("%s failed", day_iso)
        return {"date": day_iso, "error": f"{type(e).__name__}: {e}"}
    return summarize(day, segments, episodes, facts)


def days_with_raw(start: _date | None, end: _date | None) -> list[str]:
    """Corpus days holding raw segments. Today is left out unless asked for by
    ``--date``: its capture is still running, so its row would be a part-day."""
    out = []
    today = _date.today()
    for p in sorted(CORPUS_ROOT.iterdir()):
        try:
            d = _date.fromisoformat(p.name)
        except ValueError:
            continue
        if (start and d < start) or (end and d > end) or d >= today:
            continue
        if mbp1_raw_segments(d):
            out.append(p.name)
    return out


def write_rows(out: Path, rows: list[dict]) -> None:
    """Merge by date into the JSONL, newest run winning, written atomically."""
    merged: dict[str, dict] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                merged[row["date"]] = row
    for row in rows:
        merged[row["date"]] = row
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(merged[d]) + "\n" for d in sorted(merged)),
                   encoding="utf-8")
    tmp.replace(out)


def print_table(rows: list[dict]) -> None:
    print(f"# absorption reads per day at production floors "
          f"(vol>={PROD_VOL_MIN}, refills>={PROD_REFILL_MIN}); RTH = 08:30-15:00 CT")
    print(f"{'date':10s} {'symbol':10s} {'seg':>5s} {'rth_vol':>9s} {'RTH':>5s} "
          f"{'all':>5s} {'last10':>6s} {'vol p50/p90/max':>17s} {'refill p50/p90/max':>19s}  by hour CT (all)")
    print("seg = raw segments; '!' = one or more stopped decoding part-way, events before the break kept;")
    print("      '#' = a segment starts before the previous one ended, so the same tape is counted twice")
    for r in sorted(rows, key=lambda x: x["date"]):
        if "error" in r:
            print(f"{r['date']:10s} ERROR {r['error']}")
            continue
        v, k = r["rth_aggressive_vol"], r["rth_refill_events"]
        hours = " ".join(f"{h}:{n}" for h, n in r["reads_by_hour_ct"].items())
        seg = f"{r['segments']}{'!' if r['unreadable'] else ''}{'#' if r['overlapping'] else ''}"
        print(f"{r['date']:10s} {'/'.join(r['symbols']):10s} {seg:>5s} "
              f"{r['rth_trade_volume']:>9,d} {r['reads_rth']:>5d} {r['reads_all']:>5d} "
              f"{r['reads_rth_last_ten_min']:>6d} "
              f"{v['p50']:>5d}/{v['p90']:>5d}/{v['max']:>5d} "
              f"{k['p50']:>6d}/{k['p90']:>5d}/{k['max']:>5d}  {hours}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Absorption read-rate survey over raw MBP-1 days")
    parser.add_argument("--date", help="one day, YYYY-MM-DD")
    parser.add_argument("--from", dest="start", help="first day, YYYY-MM-DD")
    parser.add_argument("--to", dest="end", help="last day, YYYY-MM-DD")
    parser.add_argument("--jobs", type=int, default=4,
                        help="days surveyed in parallel (default 4; measured ~135 MB and ~20 s per day)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.date:
        days = [args.date]
    else:
        days = days_with_raw(_date.fromisoformat(args.start) if args.start else None,
                             _date.fromisoformat(args.end) if args.end else None)
    if not days:
        logger.error("no days with raw MBP-1 segments in range")
        return 1
    logger.info("surveying %d day(s), %d at a time", len(days), args.jobs)

    rows: list[dict] = []
    if args.jobs <= 1 or len(days) == 1:
        for d in days:
            rows.append(survey_day(d))
            logger.info("%s done", d)
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(survey_day, d): d for d in days}
            for fut in as_completed(futures):
                rows.append(fut.result())
                logger.info("%s done", futures[fut])

    write_rows(args.out, rows)
    print_table(rows)
    failed = [r["date"] for r in rows if "error" in r]
    if failed:
        logger.error("%d day(s) failed: %s", len(failed), ", ".join(failed))
        return 2
    logger.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
