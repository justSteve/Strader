"""OPRA NBBO for the final fifteen — the quotes leg the corpus never held. [st-byif, st-ro04]

WHY
    Every OPRA record on disk is `schema: trades`. That is why st-ro04 had to
    report the spread as an unmeasurable hole: entries at the ask and exits at
    the bid are not computable from prints at any sample size, so every multiple
    in that study is a print-to-print UPPER BOUND on an achievable one. On a
    lottery-shaped trade the spread is a larger tax than usual, so the bound is
    not a small correction.

    This closes it. cbbo-1s (consolidated BBO, one-second) over 14:45-15:00 CT,
    narrowed to the strikes within +/-40 points of the 14:45 spot.

WHAT IT COSTS, measured 2026-08-30 with metadata.get_cost on four days spanning
the corpus (2025-05-27, 2025-10-07, 2026-02-20, 2026-08-14): $0.0044-$0.0053 a
day, mean $0.00485, 2.4-2.8 MB. Across all 274 usable days that is **$1.33 and
0.71 GB**. Narrowing is what makes it cheap — the same window on full SPXW.OPT
parent symbology quotes at $1.60 a day, about 330x more, and those ~34 strikes
already carry roughly three quarters of SPXW print volume in the final fifteen.
Steve authorised the single-dollar level 2026-08-30.

    Reachability was settled the same day by a real get_range, not a quote:
    OPRA.PILLAR cbbo-1s on 2026-08-13 returned 200 OK with 420,720 records.
    `metadata.get_cost` keeps answering after a billing lapse and can never
    settle that question; only the fetch can. The 2026-08-14T13:30Z boundary in
    the 08-14 manifest is a RECENCY limit — historical OPRA before it is
    reachable with no plan.

WHAT IT WILL NOT DO
    It never touches `databento_opra.jsonl`. corpus_backfill_databento.py
    appends to a day that already holds an OPRA file, unsorted, so writing
    quotes into the trades stream would corrupt 274 days of prints. Quotes get
    their own stream, `databento_opra_quotes.jsonl.gz`, and their own manifest
    record carrying `window_ct` and `schema` — which is COO's requirement (1)
    on st-byif, satisfied for this stream on the way in rather than after.

    It is resumable: a day whose output already exists and is non-empty is
    skipped, so an interrupted run costs nothing to restart.

    It has a hard budget ceiling. The run aborts before any day that would
    carry the running total past --budget (default $3.00, against a measured
    estimate of $1.33). A quote that comes back above --max-day is refused for
    that day and recorded, never silently paid.

RUN
    .venv/bin/python3 scripts/corpus_pull_opra_quotes.py --dry-run     # quote everything, pull nothing
    .venv/bin/python3 scripts/corpus_pull_opra_quotes.py               # pull
    .venv/bin/python3 scripts/corpus_pull_opra_quotes.py --days 2026-08-14,2026-08-13
"""
from __future__ import annotations

import argparse
import functools
import gzip
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from market.corpus.writer import update_manifest, utc_now_iso  # noqa: E402
from scripts.corpus_pull_databento import _load_env  # noqa: E402

CT = ZoneInfo("America/Chicago")
DATASET = "OPRA.PILLAR"
SCHEMA = "cbbo-1s"
STREAM = "databento_opra_quotes"
PREMIUM = "data/measurement/final-fifteen-premium-2026-08-30.jsonl"
STRIKE_HALF_WIDTH = 40      # points either side of the 14:45 spot
STRIKE_STEP = 5
START_CT, END_CT = time(14, 45), time(15, 0)


# unbuffered: a long quote sweep must show progress, not appear hung
print = functools.partial(__builtins__["print"] if isinstance(__builtins__, dict) else __builtins__.print, flush=True)


def out_path(day: str) -> Path:
    return REPO / "data" / "corpus" / day / f"{STREAM}.jsonl.gz"


def symbols_for(day: str, spot: float) -> list[str]:
    d = date.fromisoformat(day)
    exp = f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"
    lo = int((spot - STRIKE_HALF_WIDTH) // STRIKE_STEP * STRIKE_STEP)
    hi = int((spot + STRIKE_HALF_WIDTH) // STRIKE_STEP * STRIKE_STEP) + STRIKE_STEP
    return [f"SPXW  {exp}{cp}{int(k * 1000):08d}"
            for k in range(lo, hi, STRIKE_STEP) for cp in ("C", "P")]


def window(day: str) -> tuple[datetime, datetime]:
    d = date.fromisoformat(day)
    return (datetime.combine(d, START_CT, tzinfo=CT).astimezone(timezone.utc),
            datetime.combine(d, END_CT, tzinfo=CT).astimezone(timezone.utc))


def pick(row, cols, *names):
    """First present column among `names` — cbbo-1s spells the top of book
    bid_px_00/ask_px_00 in some builds and bid_px/ask_px in others."""
    for n in names:
        if n in cols:
            v = row.get(n)
            return None if v is None else v
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="OPRA NBBO for the final fifteen")
    ap.add_argument("--premium", default=PREMIUM,
                    help="final-fifteen-premium jsonl — supplies the 14:45 spot per day")
    ap.add_argument("--days", default=None, help="comma-separated subset")
    ap.add_argument("--budget", type=float, default=3.00, help="hard ceiling, USD")
    ap.add_argument("--max-day", type=float, default=0.05, help="refuse a day quoting above this")
    ap.add_argument("--dry-run", action="store_true", help="quote every day, pull nothing")
    args = ap.parse_args()

    spots: dict[str, float] = {}
    for line in open(args.premium):
        r = json.loads(line)
        if "skip" not in r and r.get("spx1445"):
            spots[r["day"]] = r["spx1445"]
    days = sorted(spots) if not args.days else [d for d in args.days.split(",") if d in spots]
    if not days:
        print("no days", file=sys.stderr)
        return 2

    _load_env()
    import databento as db
    client = db.Historical()

    spent = 0.0
    pulled = skipped = refused = failed = 0
    print(f"{len(days)} days · {DATASET}/{SCHEMA} · "
          f"{START_CT:%H:%M}-{END_CT:%H:%M} CT · +/-{STRIKE_HALF_WIDTH} pts · "
          f"budget ${args.budget:.2f}{' · DRY RUN' if args.dry_run else ''}")

    for day in days:
        dest = out_path(day)
        if dest.exists() and dest.stat().st_size > 0:
            skipped += 1
            continue
        syms = symbols_for(day, spots[day])
        start, end = window(day)
        try:
            cost = client.metadata.get_cost(dataset=DATASET, symbols=syms, schema=SCHEMA,
                                            stype_in="raw_symbol", start=start, end=end)
        except Exception as e:
            print(f"  {day}  QUOTE FAILED {type(e).__name__}: {str(e)[:90]}")
            failed += 1
            continue

        if cost > args.max_day:
            print(f"  {day}  REFUSED — quotes ${cost:.4f}, above --max-day ${args.max_day:.2f}")
            refused += 1
            continue
        if spent + cost > args.budget:
            print(f"  {day}  STOP — ${spent:.4f} spent, this day ${cost:.4f}, "
                  f"budget ${args.budget:.2f}. {len(days) - pulled - skipped} days unpulled.")
            break
        if args.dry_run:
            spent += cost
            print(f"  {day}  would pull {len(syms)} syms for ${cost:.5f}  (running ${spent:.4f})")
            continue

        try:
            store = client.timeseries.get_range(dataset=DATASET, symbols=syms, schema=SCHEMA,
                                                stype_in="raw_symbol", start=start, end=end)
            df = store.to_df()
        except Exception as e:
            print(f"  {day}  PULL FAILED {type(e).__name__}: {str(e)[:90]}")
            update_manifest(d=date.fromisoformat(day), stream=STREAM, errors=[str(e)])
            failed += 1
            continue

        spent += cost
        cols = set(df.columns)
        ts_pull = utc_now_iso()
        dest.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with gzip.open(dest, "wt") as f:
            for _, row in df.iterrows():
                ts_event = row.get("ts_event") if "ts_event" in cols else row.name
                f.write(json.dumps({
                    "ts_pull_utc": ts_pull,
                    "stream": STREAM,
                    "provenance": {
                        "dataset": DATASET, "schema": SCHEMA,
                        "ts_event": ts_event.isoformat() if hasattr(ts_event, "isoformat") else str(ts_event),
                    },
                    "data": {
                        "symbol": row.get("symbol") if "symbol" in cols else None,
                        "bid_px": pick(row, cols, "bid_px_00", "bid_px"),
                        "ask_px": pick(row, cols, "ask_px_00", "ask_px"),
                        "bid_sz": pick(row, cols, "bid_sz_00", "bid_sz"),
                        "ask_sz": pick(row, cols, "ask_sz_00", "ask_sz"),
                    },
                }, default=str) + "\n")
                n += 1
        update_manifest(
            d=date.fromisoformat(day), stream=STREAM, increment_cycles=n,
            note=(f"quotes pull {START_CT:%H:%M}-{END_CT:%H:%M} CT, schema={SCHEMA}, "
                  f"{len(syms)} raw symbols within +/-{STRIKE_HALF_WIDTH}pts of "
                  f"{spots[day]:.2f}, window_ct={START_CT:%H:%M}-{END_CT:%H:%M}, "
                  f"cost_usd={cost:.5f} [st-byif]"),
        )
        pulled += 1
        print(f"  {day}  {n:>7,} quotes  ${cost:.5f}  running ${spent:.4f}  -> {dest.name}")

    print(f"\n{'quoted' if args.dry_run else 'pulled'} {pulled} · skipped {skipped} "
          f"· refused {refused} · failed {failed} · "
          f"{'estimated' if args.dry_run else 'spent'} ${spent:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
