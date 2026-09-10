#!/usr/bin/env python3
"""Repair a corpus day whose tape was written by TWO LIVE writers for a span. [st-7kwg]

WHY THIS EXISTS
---------------
`scripts/corpus_repair_doubled_day.py` repairs the other doubling: a T+1 batch
pull appended over a live tape, where the rows to drop identify themselves by
provenance (no `source: live`). This one repairs the doubling a reboot made on
2026-09-08: `strader-capture-evening.service` carried `WantedBy=multi-user.target`
and started at the 03:06 boot beside `strader-capture.service`, so two live
streamers appended the same prints to one file until the evening unit was
stopped at 06:45. Every row says `live`; nothing in provenance tells the two
writers apart. Measured (st-7kwg): trades and depth both at 49-50% duplicate
rows per half hour from 03:00 to 06:30 CT, 0.1-0.3% everywhere else.

WHAT A DUPLICATE IS HERE
------------------------
Two rows that are byte-identical once `ts_pull_utc` — the only field the
writer stamps itself — is removed: same `provenance.ts_event` to the
nanosecond, same payload. Distinct prints do occasionally collide on that key
(the ~0.3% baseline on a clean day), and those are left alone too, because the
repair only touches the span where the doubling is measured.

THE GUARD IS THE POINT
----------------------
Rows are dropped only inside a span, and only when the survey proves the span
is doubled: its duplicate share must reach `--min-span-share` (default 0.35)
and the share OUTSIDE the span must stay under `--max-outside-share` (default
0.05). A file that is 50% duplicate everywhere is a different defect and is
refused; so is a span that is not actually doubled. The span is either given
(`--from-ct`/`--to-ct`, CT wall clock) or found: the contiguous run of minutes
whose duplicate share is >= `--min-span-share`, padded by nothing. Both are
reported before anything is written.

Unparseable lines (the 2026-09-08 trades tape holds one line of NUL bytes at
row 13,888 — the same scrambled line the footprint feeder died on 73 times)
are dropped with the duplicates and counted separately.

Dry-run is the default; `--apply` is required to write. The rewrite goes to a
temp file beside the original, is fsynced, and lands by os.replace; the
manifest's cycle count is SET to what the tape now holds, under the writer's
lock, with a repair record and a note.

USAGE
-----
    .venv/bin/python scripts/corpus_repair_doubled_span.py --date 2026-09-08 \
        --stream databento_glbx_es
    .venv/bin/python scripts/corpus_repair_doubled_span.py --date 2026-09-08 \
        --stream databento_glbx_es_mbp1 --apply

Exit codes: 0 clean or repaired, 1 refused by a guard, 2 nothing to repair,
3 usage/IO error.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from market.corpus.paths import day_dir, manifest_path, resolve_existing  # noqa: E402
from market.corpus.writer import rewrite_manifest, utc_now_iso  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
PULL_FIELD = re.compile(rb'"ts_pull_utc": "[^"]*", ?')
TS_EVENT = re.compile(rb'"ts_event": "(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)')
DEFAULT_MIN_SPAN_SHARE = 0.35
DEFAULT_MAX_OUTSIDE_SHARE = 0.05


class RepairError(Exception):
    """Usage or IO fault — distinct from a guard refusal, which is a verdict."""


def open_lines(path: Path):
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def row_key(line: bytes) -> bytes:
    """The writer-independent identity of a row: everything but ts_pull_utc."""
    return hashlib.blake2b(PULL_FIELD.sub(b"", line, count=1), digest_size=16).digest()


def is_row(line: bytes) -> bool:
    """A corpus row is one JSON object per line. The scrambled line the
    2026-09-08 outage left is a run of NUL bytes ahead of a row; a partial
    write is a line with no closing brace. Neither is a row."""
    body = line.rstrip(b"\r\n")
    return body.startswith(b"{") and body.endswith(b"}") and b"\x00" not in body


def row_minute(line: bytes) -> int | None:
    """Minute-of-day in CT for the row's provenance.ts_event, or None for a
    line that is not a row."""
    if not is_row(line):
        return None
    m = TS_EVENT.search(line)
    if not m:
        return None
    y, mo, d, hh, mm = (int(x) for x in m.groups())
    try:
        t = datetime(y, mo, d, hh, mm, tzinfo=timezone.utc).astimezone(CENTRAL)
    except ValueError:
        return None
    return t.hour * 60 + t.minute


def parse_ct(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh) * 60 + int(mm)


def fmt_minute(m: int | None) -> str:
    return "-" if m is None else f"{m // 60:02d}:{m % 60:02d}"


class Survey:
    def __init__(self) -> None:
        self.rows_by_minute: dict[int, int] = {}
        self.dups_by_minute: dict[int, int] = {}
        self.n_unparsed = 0
        self.total = 0
        self.span: tuple[int, int] | None = None

    def rows_in(self, lo: int, hi: int) -> int:
        return sum(v for k, v in self.rows_by_minute.items() if lo <= k <= hi)

    def dups_in(self, lo: int, hi: int) -> int:
        return sum(v for k, v in self.dups_by_minute.items() if lo <= k <= hi)

    @property
    def span_rows(self) -> int:
        return self.rows_in(*self.span) if self.span else 0

    @property
    def span_dups(self) -> int:
        return self.dups_in(*self.span) if self.span else 0

    @property
    def span_share(self) -> float:
        return self.span_dups / self.span_rows if self.span_rows else 0.0

    @property
    def outside_rows(self) -> int:
        return self.total - self.n_unparsed - self.span_rows

    @property
    def outside_dups(self) -> int:
        return sum(self.dups_by_minute.values()) - self.span_dups

    @property
    def outside_share(self) -> float:
        return self.outside_dups / self.outside_rows if self.outside_rows else 0.0


def survey(path: Path, span: tuple[int, int] | None, *, min_share: float) -> Survey:
    """One pass: per-minute row and duplicate counts (first occurrence wins).
    Then the span is either the one given or the longest contiguous run of
    minutes at or above ``min_share`` — a doubled stretch is a plateau, not a
    scatter."""
    s = Survey()
    seen: set[bytes] = set()
    with open_lines(path) as fh:
        for line in fh:
            s.total += 1
            minute = row_minute(line)
            if minute is None:
                s.n_unparsed += 1
                continue
            s.rows_by_minute[minute] = s.rows_by_minute.get(minute, 0) + 1
            k = row_key(line)
            if k in seen:
                s.dups_by_minute[minute] = s.dups_by_minute.get(minute, 0) + 1
            else:
                seen.add(k)
    if span is not None:
        s.span = span
        return s
    best: tuple[int, int] | None = None
    run_start: int | None = None
    prev: int | None = None
    for minute in sorted(s.rows_by_minute):
        share = s.dups_by_minute.get(minute, 0) / s.rows_by_minute[minute]
        hot = share >= min_share
        if hot and (run_start is None or prev is None or minute != prev + 1):
            run_start = minute
        if hot:
            if best is None or (minute - run_start) > (best[1] - best[0]):
                best = (run_start, minute)
        else:
            run_start = None
        prev = minute if hot else None
    s.span = best
    return s


def rewrite_without_span_duplicates(path: Path, span: tuple[int, int], *,
                                    expect_keep: int) -> int:
    """Rewrite ``path`` keeping the first occurrence of every row inside the
    span and every parseable row outside it. Returns rows kept."""
    lo, hi = span
    tmp = path.with_suffix(path.suffix + ".repair-tmp")
    opener = gzip.open if path.suffix == ".gz" else open
    kept = 0
    seen: set[bytes] = set()
    try:
        with open_lines(path) as src, opener(tmp, "wb") as dst:
            for line in src:
                minute = row_minute(line)
                if minute is None:
                    continue
                if lo <= minute <= hi:
                    k = row_key(line)
                    if k in seen:
                        continue
                    seen.add(k)
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
            f"rewrite kept {kept:,} rows but the survey expected {expect_keep:,} — "
            "the file changed under the repair; nothing was replaced"
        )
    os.replace(tmp, path)
    return kept


def update_manifest_after_repair(d: date, stream: str, *, kept: int, dropped: int,
                                 unparsed: int, span: tuple[int, int], note: str) -> None:
    def edit(manifest: dict) -> None:
        s = manifest["streams"].setdefault(stream, {"cycles": 0, "errors": []})
        s["cycles"] = kept
        s["repaired_utc"] = utc_now_iso()
        s["repair"] = {
            "dropped_duplicate_rows": dropped,
            "dropped_unparseable_rows": unparsed,
            "kept_rows": kept,
            "span_ct": f"{fmt_minute(span[0])}-{fmt_minute(span[1])}",
        }
        manifest.setdefault("notes", []).append(
            {"ts": utc_now_iso(), "stream": stream, "note": note}
        )
    rewrite_manifest(d, edit, path=manifest_path(d))


def report(s: Survey, path: Path, *, min_share: float, max_outside: float) -> None:
    print(f"tape        : {path}")
    print(f"rows        : {s.total:,}  (unparsed {s.n_unparsed:,})")
    if s.span is None:
        print(f"doubled span: none found (no minute at or above {min_share:.0%} duplicate share)")
        return
    lo, hi = s.span
    print(f"doubled span: {fmt_minute(lo)}-{fmt_minute(hi)} CT  rows {s.span_rows:,}  "
          f"duplicates {s.span_dups:,}  share {s.span_share:.1%}  (limit >= {min_share:.0%})")
    print(f"outside span: rows {s.outside_rows:,}  duplicates {s.outside_dups:,}  "
          f"share {s.outside_share:.2%}  (limit <= {max_outside:.0%})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Drop the second writer's rows from a span two live "
                    "streamers wrote at once, but only when the survey proves "
                    "the span is doubled.")
    ap.add_argument("--date", required=True, help="corpus day, YYYY-MM-DD (US/Central)")
    ap.add_argument("--stream", required=True, help="stream name, e.g. databento_glbx_es")
    ap.add_argument("--from-ct", help="span start HH:MM CT (default: find the doubled run)")
    ap.add_argument("--to-ct", help="span end HH:MM CT, inclusive minute")
    ap.add_argument("--apply", action="store_true", help="write the repair (default is a dry run)")
    ap.add_argument("--min-span-share", type=float, default=DEFAULT_MIN_SPAN_SHARE,
                    help=f"refuse unless the span's duplicate share reaches this "
                         f"(default {DEFAULT_MIN_SPAN_SHARE})")
    ap.add_argument("--max-outside-share", type=float, default=DEFAULT_MAX_OUTSIDE_SHARE,
                    help=f"refuse if the duplicate share outside the span exceeds this "
                         f"(default {DEFAULT_MAX_OUTSIDE_SHARE})")
    args = ap.parse_args(argv)

    try:
        d = date.fromisoformat(args.date)
    except ValueError:
        print(f"bad --date {args.date!r}", file=sys.stderr)
        return 3
    if bool(args.from_ct) != bool(args.to_ct):
        print("--from-ct and --to-ct go together", file=sys.stderr)
        return 3
    span = (parse_ct(args.from_ct), parse_ct(args.to_ct)) if args.from_ct else None
    path = resolve_existing(day_dir(d) / f"{args.stream}.jsonl")
    if path is None:
        print(f"no tape for {args.stream} on {d}", file=sys.stderr)
        return 3

    try:
        s = survey(path, span, min_share=args.min_span_share)
    except OSError as e:
        print(f"cannot read {path}: {e}", file=sys.stderr)
        return 3
    report(s, path, min_share=args.min_span_share, max_outside=args.max_outside_share)

    if s.span is None or (s.span_dups == 0 and s.n_unparsed == 0):
        print("verdict     : nothing to repair")
        return 2
    if s.span_share < args.min_span_share:
        print(f"verdict     : REFUSED — span duplicate share {s.span_share:.1%} is below "
              f"{args.min_span_share:.0%}; this span is not doubled")
        return 1
    if s.outside_share > args.max_outside_share:
        print(f"verdict     : REFUSED — {s.outside_share:.2%} duplicates outside the span; "
              "the doubling is not confined to it and this tool does not apply")
        return 1

    drop = s.span_dups + s.n_unparsed
    keep = s.total - drop
    print(f"repair      : drop {s.span_dups:,} duplicate rows in the span and "
          f"{s.n_unparsed:,} unparseable rows; keep {keep:,}")
    if not args.apply:
        print("verdict     : dry run — pass --apply to write")
        return 0

    kept = rewrite_without_span_duplicates(path, s.span, expect_keep=keep)
    note = (f"repaired [st-7kwg]: two live writers {fmt_minute(s.span[0])}-"
            f"{fmt_minute(s.span[1])} CT; dropped {s.span_dups:,} duplicate rows "
            f"({s.span_share:.1%} of the span) and {s.n_unparsed:,} unparseable; "
            f"{kept:,} rows remain")
    update_manifest_after_repair(d, args.stream, kept=kept, dropped=s.span_dups,
                                 unparsed=s.n_unparsed, span=s.span, note=note)
    print(f"verdict     : REPAIRED — {kept:,} rows kept, manifest cycles set")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RepairError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(3)
