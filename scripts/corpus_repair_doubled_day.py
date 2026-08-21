#!/usr/bin/env python3
"""Repair a corpus day whose tape carries a duplicate batch pull. [co-j5qzq]

WHY THIS EXISTS, AND WHY IT BREAKS THE APPEND-ONLY RULE
-------------------------------------------------------
`market/corpus/writer.py` says it plainly: "Append-only by design: history is
the value. No row is ever modified or removed." That rule protects HISTORY. A
doubled tape is not history — it is the same six and a half hours of market
written down twice, and every consumer that counts, sums, or measures density
over it reads a market that never happened. The 2026-08-11 trades incident and
the 2026-08-19 depth incident are the same defect (Watcher V2 Risk 15): a
health check that tested whether a live stream was HEALTHY, not whether it had
ROWS, so the T+1 batch pull ran anyway and appended onto a tape that already
held the session.

The write-side fault is fixed (scripts/corpus_daily.py, 013832e). This is the
read-side repair for days that were already written.

WHAT IT DOES
------------
Records carry their origin in `provenance`: a live-streamed row has
`provenance.source == "live"`, a batch-pulled row does not (it also names the
continuous symbol as its `data.symbol`, e.g. ES.c.0, where live rows name the
resolved contract, e.g. ESU6). The repair drops the batch rows — but only
after proving the live tape actually covers the window the batch rows span.

THE GUARD IS THE POINT
----------------------
Dropping a duplicate leaves a clean day. Dropping a batch pull that was
covering a real hole in the live capture leaves a HOLE, which is worse, and
which no later consumer can see. So the tool refuses to drop anything unless,
across the batch span:

  * the live tape has no gap longer than --max-gap-seconds, and
  * live rows number at least --min-live-ratio of the batch rows.

Both are reported whether or not they pass. A refusal names the gap, and the
right repair then is a windowed re-pull over just that gap, not this tool.

Dry-run is the default; `--apply` is required to write. The rewrite goes to a
temp file beside the original, is fsynced, and lands by os.replace, so an
interrupted run leaves the original untouched.

USAGE
-----
    python3 scripts/corpus_repair_doubled_day.py --date 2026-08-19 \
        --stream databento_glbx_es_mbp1
    python3 scripts/corpus_repair_doubled_day.py --date 2026-08-19 \
        --stream databento_glbx_es_mbp1 --apply

Exit codes: 0 clean or repaired, 1 refused by a guard, 2 nothing to repair
(no batch rows), 3 usage/IO error.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import day_dir, manifest_path, resolve_existing  # noqa: E402
from market.corpus.writer import utc_now_iso  # noqa: E402

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
LIVE_MARKER = b'"source": "live"'
TS_KEY = b'"ts_event": "'

# Defaults. A gap of a minute in a depth tape is an outage worth re-pulling;
# ordinary quiet-tape spacing on ES MBP-1 is under a handful of seconds even
# overnight. The ratio is deliberately loose — the two sources index the same
# market but not row-for-row, so an exact match is not expected.
DEFAULT_MAX_GAP_SECONDS = 60.0
DEFAULT_MIN_LIVE_RATIO = 0.90


class RepairError(Exception):
    """Usage or IO fault — distinct from a guard refusal, which is a verdict."""


def parse_ts_event(line: bytes) -> int | None:
    """Nanoseconds since epoch from a record's provenance.ts_event, or None.

    Byte-level on purpose: this runs over multi-gigabyte tapes (2026-08-19
    depth is 6.0 GB / 12.4M rows) and json.loads per row costs minutes where
    this costs seconds. Handles both `...:SS+00:00` and
    `...:SS.fffffffff+00:00`; nanosecond precision is preserved because
    Databento emits it and two rows can share a microsecond.
    """
    i = line.find(TS_KEY)
    if i < 0:
        return None
    j = i + len(TS_KEY)
    try:
        y = int(line[j:j + 4])
        mo = int(line[j + 5:j + 7])
        d = int(line[j + 8:j + 10])
        hh = int(line[j + 11:j + 13])
        mm = int(line[j + 14:j + 16])
        ss = int(line[j + 17:j + 19])
    except ValueError:
        return None
    k = j + 19
    frac_ns = 0
    if line[k:k + 1] == b".":
        k += 1
        start = k
        while line[k:k + 1].isdigit():
            k += 1
        frac_ns = int((line[start:k].decode() + "000000000")[:9])
    try:
        base = datetime(y, mo, d, hh, mm, ss, tzinfo=timezone.utc)
    except ValueError:
        return None
    return int((base - EPOCH).total_seconds()) * 1_000_000_000 + frac_ns


def is_live(line: bytes) -> bool:
    return LIVE_MARKER in line


def fmt_ns(ns: int | None) -> str:
    if ns is None:
        return "-"
    return (EPOCH + timedelta(microseconds=ns // 1000)).isoformat()


def open_lines(path: Path):
    """Binary line iterator over a corpus JSONL, .gz aware."""
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return path.open("rb")


class Survey:
    """What one pass over the tape found."""

    def __init__(self) -> None:
        self.n_live = 0
        self.n_batch = 0
        self.n_unparsed = 0
        self.live_first: int | None = None
        self.live_last: int | None = None
        self.batch_first: int | None = None
        self.batch_last: int | None = None
        self.live_in_span = 0
        self.max_gap_ns = 0
        self.max_gap_at: int | None = None
        self.out_of_order = 0

    @property
    def total(self) -> int:
        return self.n_live + self.n_batch + self.n_unparsed

    @property
    def max_gap_seconds(self) -> float:
        return self.max_gap_ns / 1e9

    @property
    def live_ratio(self) -> float:
        if self.n_batch == 0:
            return 1.0
        return self.live_in_span / self.n_batch


def survey(path: Path) -> Survey:
    """Two passes: find the batch span, then measure live coverage of it.

    Two passes rather than one because the live-gap measurement has to be
    scoped to the batch span, and the span is only known once the whole file
    has been read. Each pass is a sequential scan; on 6 GB the pair costs
    about 90 seconds.
    """
    s = Survey()
    with open_lines(path) as fh:
        for line in fh:
            t = parse_ts_event(line)
            if t is None:
                s.n_unparsed += 1
                continue
            if is_live(line):
                s.n_live += 1
                if s.live_first is None:
                    s.live_first = t
                s.live_last = t
            else:
                s.n_batch += 1
                if s.batch_first is None:
                    s.batch_first = t
                s.batch_last = t

    if s.n_batch == 0 or s.batch_first is None or s.batch_last is None:
        return s

    lo, hi = s.batch_first, s.batch_last
    prev: int | None = None
    with open_lines(path) as fh:
        for line in fh:
            if not is_live(line):
                continue
            t = parse_ts_event(line)
            if t is None or not (lo <= t <= hi):
                continue
            s.live_in_span += 1
            if prev is not None:
                gap = t - prev
                if gap < 0:
                    s.out_of_order += 1
                elif gap > s.max_gap_ns:
                    s.max_gap_ns, s.max_gap_at = gap, prev
            prev = t
    return s


def rewrite_without_batch(path: Path, expect_keep: int) -> int:
    """Rewrite ``path`` keeping only live rows. Returns rows kept.

    Temp file beside the original (same filesystem, so os.replace is atomic),
    fsynced before the rename. A crash mid-write leaves the original in place
    and a .repair-tmp beside it.
    """
    tmp = path.with_suffix(path.suffix + ".repair-tmp")
    kept = 0
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with open_lines(path) as src, opener(tmp, "wb") as dst:
            for line in src:
                if is_live(line):
                    dst.write(line)
                    kept += 1
            dst.flush()
            if hasattr(dst, "fileno"):
                os.fsync(dst.fileno())
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    if kept != expect_keep:
        tmp.unlink(missing_ok=True)
        raise RepairError(
            f"rewrite kept {kept:,} rows but the survey counted {expect_keep:,} live "
            "rows — the file changed under the repair; nothing was replaced"
        )
    os.replace(tmp, path)
    return kept


def update_manifest_after_repair(
    d: date, stream: str, *, kept: int, dropped: int, note: str
) -> None:
    """Set the stream's cycle count to what the tape now holds and record why.

    Deliberately a SET, not the writer's increment — the count was wrong, and
    an increment cannot express that. `repaired_utc` and the note leave the
    event legible to anyone who reads the manifest later.
    """
    path = manifest_path(d)
    manifest = json.loads(path.read_text())
    s = manifest["streams"].setdefault(stream, {"cycles": 0, "errors": []})
    s["cycles"] = kept
    s["repaired_utc"] = utc_now_iso()
    s["repair"] = {"dropped_batch_rows": dropped, "kept_live_rows": kept}
    manifest.setdefault("notes", []).append(
        {"ts": utc_now_iso(), "stream": stream, "note": note}
    )
    path.write_text(json.dumps(manifest, indent=2))


def report(s: Survey, path: Path, *, max_gap: float, min_ratio: float) -> None:
    print(f"tape        : {path}")
    print(f"rows        : {s.total:,}  (live {s.n_live:,}, batch {s.n_batch:,}, "
          f"unparsed {s.n_unparsed:,})")
    print(f"live span   : {fmt_ns(s.live_first)} -> {fmt_ns(s.live_last)}")
    print(f"batch span  : {fmt_ns(s.batch_first)} -> {fmt_ns(s.batch_last)}")
    if s.n_batch:
        print(f"live rows inside the batch span : {s.live_in_span:,} "
              f"({s.live_ratio * 100:.2f}% of the batch's {s.n_batch:,})")
        print(f"largest live gap in that span   : {s.max_gap_seconds:.3f} s "
              f"at {fmt_ns(s.max_gap_at)}   (limit {max_gap:g} s)")
        print(f"out-of-order live timestamps    : {s.out_of_order:,}")
        print(f"coverage ratio limit            : {min_ratio:.2f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Drop a duplicate batch pull from a corpus day, "
                    "but only when the live tape provably covers it."
    )
    ap.add_argument("--date", required=True, help="corpus day, YYYY-MM-DD (US/Central)")
    ap.add_argument("--stream", required=True,
                    help="stream name, e.g. databento_glbx_es_mbp1")
    ap.add_argument("--apply", action="store_true",
                    help="write the repair (default is a dry run)")
    ap.add_argument("--max-gap-seconds", type=float, default=DEFAULT_MAX_GAP_SECONDS,
                    help=f"refuse if the live tape has a gap longer than this "
                         f"inside the batch span (default {DEFAULT_MAX_GAP_SECONDS:g})")
    ap.add_argument("--min-live-ratio", type=float, default=DEFAULT_MIN_LIVE_RATIO,
                    help=f"refuse if live rows in the span are fewer than this "
                         f"fraction of batch rows (default {DEFAULT_MIN_LIVE_RATIO})")
    args = ap.parse_args(argv)

    try:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"error: --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        return 3

    raw = day_dir(d) / f"{args.stream}.jsonl"
    path = resolve_existing(raw)
    if path is None:
        print(f"error: no corpus file at {raw} (nor {raw}.gz)", file=sys.stderr)
        return 3

    s = survey(path)
    report(s, path, max_gap=args.max_gap_seconds, min_ratio=args.min_live_ratio)

    if s.n_batch == 0:
        print("\nNOTHING TO REPAIR — the tape holds no batch-provenance rows.")
        return 2

    if s.n_live == 0:
        print("\nREFUSED — the tape is batch-only. There is no live tape to fall "
              "back to, so these rows are the day's only record.", file=sys.stderr)
        return 1

    failures = []
    if s.max_gap_seconds > args.max_gap_seconds:
        failures.append(
            f"live tape has a {s.max_gap_seconds:.3f} s gap at {fmt_ns(s.max_gap_at)} "
            f"(limit {args.max_gap_seconds:g} s)"
        )
    if s.live_ratio < args.min_live_ratio:
        failures.append(
            f"live rows cover only {s.live_ratio * 100:.2f}% of the batch row count "
            f"(limit {args.min_live_ratio * 100:.0f}%)"
        )
    if failures:
        print("\nREFUSED — dropping the batch rows would leave a hole:", file=sys.stderr)
        for f in failures:
            print(f"  * {f}", file=sys.stderr)
        print("  Repair the gap with a windowed --force re-pull over just that "
              "window instead.", file=sys.stderr)
        return 1

    print(f"\nGUARDS PASS — the live tape covers the batch span. "
          f"{s.n_batch:,} batch rows are a duplicate of it.")

    if not args.apply:
        print("DRY RUN — nothing written. Re-run with --apply to drop them.")
        return 0

    note = (
        f"REPAIR [co-j5qzq]: dropped {s.n_batch:,} duplicate batch-pull rows "
        f"({fmt_ns(s.batch_first)} -> {fmt_ns(s.batch_last)}) appended onto a live "
        f"tape that already held the window; live coverage verified first "
        f"(largest gap {s.max_gap_seconds:.3f}s, {s.live_in_span:,} live rows in "
        f"span). Kept {s.n_live:,} live rows."
    )
    kept = rewrite_without_batch(path, s.n_live)
    update_manifest_after_repair(d, args.stream, kept=kept, dropped=s.n_batch, note=note)
    print(f"REPAIRED — kept {kept:,} live rows, dropped {s.n_batch:,} batch rows.")
    print(f"manifest cycles for {args.stream} set to {kept:,}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RepairError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(3)
