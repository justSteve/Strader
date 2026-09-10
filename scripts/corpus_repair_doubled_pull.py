#!/usr/bin/env python3
"""Repair a corpus day whose batch pull RAN TWICE. [st-c078]

WHY A THIRD REPAIR TOOL
-----------------------
Two repairs already exist and neither fits this shape:

* `corpus_repair_doubled_day.py` drops rows that are not `provenance.source ==
  "live"` — a batch pull appended over a live tape. On 2026-07-20 there is no
  live tape at all: every row is batch, so it refuses (measured, exit 1:
  "the tape is batch-only").
* `corpus_repair_doubled_span.py` drops repeated rows inside a doubled span,
  keyed on the row minus `ts_pull_utc`. On 2026-07-20 the doubling covers the
  whole file, so the span finder swallows the day, the "doubling outside the
  span" guard cannot fire, and the tool applies a KEYED DEDUP to a tape where
  a keyed dedup is lossy. Measured on 2026-07-20 ES: it would keep 327,440
  rows where the pull itself wrote 330,104 — 2,664 rows destroyed. Those are
  distinct prints that agree on every published field (same ts_event to the
  nanosecond, same price, size, side, sequence, flags); one aggressor filling
  two resting orders leaves exactly that pair, and both are real volume.

THE SHAPE THIS REPAIRS, AND WHY IT IS EXACTLY SEPARABLE
-------------------------------------------------------
`scripts/corpus_pull_databento_es.py` and `corpus_pull_databento.py` take
`ts_pull = utc_now_iso()` ONCE per process and stamp it on every row that run
writes, then `update_manifest(increment_cycles=tick_count)`. So a pull that
ran twice leaves two complete copies, each carrying its own `ts_pull_utc`,
and the manifest's cycle count is their SUM. Because `append_jsonl` opens,
appends and closes per row, two concurrent runs INTERLEAVE on disk — the
copies are not two contiguous halves, and "keep the first N lines" is wrong
too. Measured 2026-07-20 ES: stamps 11:30:59Z and 11:31:14Z, 330,104 rows
each, first backward jump in ts_event at row 152,795.

The stamp is what makes this exact. Dropping one run's rows leaves the other
run's output byte-for-byte as that run wrote it — including its own internal
repeats, which are data, not damage.

THE GUARD IS THE POINT
----------------------
A second `ts_pull_utc` is not by itself proof of a duplicate: a windowed
re-pull over a gap also adds a stamp, and dropping it would leave a HOLE.
So nothing is written unless every stamp's substream is provably the SAME
PULL, in one of two ways.

IDENTICAL RUNS — the pull ran twice and both finished:

  * every stamp carries the same number of rows, and
  * every stamp's rows, in file order, with `ts_pull_utc` removed, hash to
    the same digest — the runs returned identical data in identical order.

The earliest run is kept.

A PREFIX RUN — the pull was cut off and re-run in full:

  * exactly one stamp is the longest, and
  * every shorter stamp's digest equals the digest of the longest run's FIRST
    n rows, in file order, where n is that shorter run's row count.

Then the short run wrote nothing the long run did not write again, and the
LONGEST run is kept. Measured 2026-07-14 depth: stamp 18:24:33Z stopped at
4,633,761 rows (ts_event 19:22:38Z) and 18:49:25Z ran the window in full to
4,950,487; the short run's digest 3f9f7f8b18e880ec8a3691f83dd77cf0 is exactly
the long run's first 4,633,761 rows. Keying the whole file instead would keep
4,948,594 rows and lose 1,893 the completed pull actually wrote.

Any other difference — same length but different content, a shorter run that
is not a prefix, two runs tied for longest — is a different pull, and this
tool refuses.
Rows that carry no usable stamp (a NUL-scrambled line, a partial write) are
counted and refuse the repair unless `--drop-unattributable` says otherwise:
"keep one run" has no defensible answer for a row that belongs to none.

The original is copied to `<tape>.pre-repair-<utc>` beside itself before
anything is replaced (`--no-backup` to skip). The rewrite goes to a temp file,
is fsynced, and lands by os.replace; the manifest's cycle count is SET to what
the tape now holds, under the writer's lock, with a repair record and a note.

USAGE
-----
    .venv/bin/python scripts/corpus_repair_doubled_pull.py --date 2026-07-20 \\
        --stream databento_glbx_es
    .venv/bin/python scripts/corpus_repair_doubled_pull.py --date 2026-07-20 \\
        --stream databento_glbx_es --apply

Exit codes: 0 clean or repaired, 1 refused by a guard, 2 nothing to repair,
3 usage/IO error.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from market.corpus.paths import day_dir, manifest_path, resolve_existing  # noqa: E402
from market.corpus.writer import rewrite_manifest, utc_now_iso  # noqa: E402

PULL_FIELD = re.compile(rb'"ts_pull_utc": "([^"]*)", ?')
TS_EVENT = re.compile(rb'"ts_event": "([^"]+)"')
BEAD = "st-c078"


class RepairError(Exception):
    """Usage or IO fault — distinct from a guard refusal, which is a verdict."""


def open_lines(path: Path):
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def is_row(line: bytes) -> bool:
    """A corpus row is one JSON object per line. A NUL-scrambled line and a
    partial write are not rows, and carry no stamp we can trust."""
    body = line.rstrip(b"\r\n")
    return body.startswith(b"{") and body.endswith(b"}") and b"\x00" not in body


def pull_stamp(line: bytes) -> bytes | None:
    """The row's ``ts_pull_utc``, which identifies the run that wrote it."""
    if not is_row(line):
        return None
    m = PULL_FIELD.search(line)
    return m.group(1) if m else None


def row_key(line: bytes) -> bytes:
    """The run-independent content of a row: everything but ts_pull_utc."""
    return PULL_FIELD.sub(b"", line, count=1)


class Run:
    """One ``ts_pull_utc`` — one execution of the pull script."""

    def __init__(self, stamp: bytes) -> None:
        self.stamp = stamp.decode()
        self.rows = 0
        self._h = hashlib.blake2b(digest_size=16)
        self.ts_first: str | None = None
        self.ts_last: str | None = None

    def add(self, line: bytes) -> None:
        self.rows += 1
        self._h.update(row_key(line))
        m = TS_EVENT.search(line)
        if m:
            v = m.group(1).decode()
            if self.ts_first is None:
                self.ts_first = v
            self.ts_last = v

    @property
    def digest(self) -> str:
        return self._h.hexdigest()


class Survey:
    """What one streaming pass over the tape found. Memory is O(runs)."""

    def __init__(self) -> None:
        self.runs: dict[bytes, Run] = {}
        self.order: list[bytes] = []
        self.total = 0
        self.n_unattributable = 0

    def add(self, line: bytes) -> None:
        self.total += 1
        stamp = pull_stamp(line)
        if stamp is None:
            self.n_unattributable += 1
            return
        run = self.runs.get(stamp)
        if run is None:
            run = self.runs[stamp] = Run(stamp)
            self.order.append(stamp)
        run.add(line)

    @property
    def sorted_runs(self) -> list[Run]:
        """Runs in ts_pull_utc order — the earliest run is the original."""
        return [self.runs[s] for s in sorted(self.runs)]

    @property
    def counts_agree(self) -> bool:
        return len({r.rows for r in self.runs.values()}) == 1

    @property
    def content_agrees(self) -> bool:
        return len({r.digest for r in self.runs.values()}) == 1


def survey(path: Path) -> Survey:
    """One sequential pass. Nothing but the per-run accumulators is held, so a
    4.4 GB depth tape costs the same memory as a 200 MB trades tape."""
    s = Survey()
    with open_lines(path) as fh:
        for line in fh:
            s.add(line)
    return s


def longest_run(s: Survey) -> Run | None:
    """The single run with the most rows, or None if two are tied for it —
    a tie leaves no defensible "keep the complete one"."""
    ranked = sorted(s.runs.values(), key=lambda r: r.rows, reverse=True)
    if len(ranked) > 1 and ranked[0].rows == ranked[1].rows:
        return None
    return ranked[0] if ranked else None


def prefix_verdicts(path: Path, s: Survey, keep: Run) -> dict[str, bool]:
    """Is each shorter run an exact prefix of ``keep``? {stamp: True/False}

    A second sequential pass, paid only when the row counts disagree: replay
    the longest run alone, snapshotting its running digest at each shorter
    run's row count, and compare. blake2b snapshots by ``copy()``, so N
    checkpoints cost one pass, not N.
    """
    wanted: dict[int, list[Run]] = {}
    for r in s.runs.values():
        if r.stamp != keep.stamp:
            wanted.setdefault(r.rows, []).append(r)
    keep_b = keep.stamp.encode()
    h = hashlib.blake2b(digest_size=16)
    n = 0
    snaps: dict[int, str] = {}
    with open_lines(path) as fh:
        for line in fh:
            if pull_stamp(line) != keep_b:
                continue
            h.update(row_key(line))
            n += 1
            if n in wanted:
                snaps[n] = h.copy().hexdigest()
    return {r.stamp: snaps.get(cnt) == r.digest
            for cnt, rs in wanted.items() for r in rs}


def back_up(path: Path, *, stamp_utc: str) -> Path:
    """Copy the tape beside itself before anything replaces it. The name ends
    in ``.pre-repair-<utc>``, which neither the compactor's ``databento_*.jsonl``
    glob nor any stream path helper can resolve, so the backup is inert."""
    dest = path.with_name(f"{path.name}.pre-repair-{stamp_utc}")
    if dest.exists():
        raise RepairError(f"backup {dest} already exists; refusing to overwrite it")
    with path.open("rb") as src, dest.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if dest.stat().st_size != path.stat().st_size:
        dest.unlink(missing_ok=True)
        raise RepairError(f"backup of {path.name} came out a different size; nothing was replaced")
    return dest


def rewrite_keeping_run(path: Path, keep: str, *, expect_keep: int) -> int:
    """Rewrite ``path`` keeping only rows stamped ``keep``. Returns rows kept."""
    tmp = path.with_suffix(path.suffix + ".repair-tmp")
    opener = gzip.open if path.suffix == ".gz" else open
    keep_b = keep.encode()
    kept = 0
    try:
        with open_lines(path) as src, opener(tmp, "wb") as dst:
            for line in src:
                if pull_stamp(line) != keep_b:
                    continue
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
                                 unattributable: int, keep_run: Run,
                                 dropped_runs: list[Run], note: str,
                                 mode: str = "identical") -> None:
    """SET the stream's cycle count to what the tape now holds and record why.

    A SET, not the writer's increment: the count was the SUM of the runs, and
    an increment cannot express that it was wrong. The field names match the
    two sibling repairs so a reader meets one convention.
    """
    def edit(manifest: dict) -> None:
        s = manifest["streams"].setdefault(stream, {"cycles": 0, "errors": []})
        s["cycles"] = kept
        s["repaired_utc"] = utc_now_iso()
        s["repair"] = {
            "dropped_duplicate_rows": dropped,
            "dropped_unparseable_rows": unattributable,
            "kept_rows": kept,
            "kept_pull_utc": keep_run.stamp,
            "dropped_pull_utc": [r.stamp for r in dropped_runs],
            "identical_run_digest": keep_run.digest,
            "duplicate_shape": mode,
        }
        manifest.setdefault("notes", []).append(
            {"ts": utc_now_iso(), "stream": stream, "note": note}
        )
    rewrite_manifest(d, edit, path=manifest_path(d))


def report(s: Survey, path: Path) -> None:
    print(f"tape        : {path}")
    print(f"rows        : {s.total:,}  (unattributable {s.n_unattributable:,})")
    print(f"pull runs   : {len(s.runs)}")
    for r in s.sorted_runs:
        print(f"  {r.stamp}  rows {r.rows:,}  digest {r.digest}  "
              f"ts_event {r.ts_first} -> {r.ts_last}")
    if len(s.runs) > 1:
        print(f"row counts agree : {s.counts_agree}")
        print(f"content agrees   : {s.content_agrees}   "
              "(same rows, same order, ts_pull_utc removed)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Drop the duplicate copies a batch pull that ran more than "
                    "once left behind, but only when every run provably wrote "
                    "the same rows in the same order.")
    ap.add_argument("--date", required=True, help="corpus day, YYYY-MM-DD (US/Central)")
    ap.add_argument("--stream", required=True, help="stream name, e.g. databento_glbx_es")
    ap.add_argument("--apply", action="store_true", help="write the repair (default is a dry run)")
    ap.add_argument("--keep-pull", help="ts_pull_utc of the run to keep (default: the earliest)")
    ap.add_argument("--drop-unattributable", action="store_true",
                    help="drop rows that carry no usable ts_pull_utc instead of refusing")
    ap.add_argument("--no-backup", action="store_true",
                    help="do not copy the tape to <tape>.pre-repair-<utc> first")
    args = ap.parse_args(argv)

    try:
        d = date.fromisoformat(args.date)
    except ValueError:
        print(f"bad --date {args.date!r}", file=sys.stderr)
        return 3
    path = resolve_existing(day_dir(d) / f"{args.stream}.jsonl")
    if path is None:
        print(f"no tape for {args.stream} on {d}", file=sys.stderr)
        return 3

    try:
        s = survey(path)
    except OSError as e:
        print(f"cannot read {path}: {e}", file=sys.stderr)
        return 3
    report(s, path)

    if len(s.runs) < 2:
        print("verdict     : nothing to repair — the tape holds one pull run")
        return 2

    runs = s.sorted_runs
    forced: Run | None = None
    if s.counts_agree:
        if not s.content_agrees:
            print("verdict     : REFUSED — the runs are the same length but disagree on "
                  "content or order, so they are not copies of one pull; dropping one "
                  "would leave a hole", file=sys.stderr)
            return 1
        mode = "identical"
    else:
        # Row counts disagree. The only shape that is still lossless to repair
        # is a pull that was cut off and re-run in full.
        forced = longest_run(s)
        if forced is None:
            print("verdict     : REFUSED — two runs are tied for longest, so there is no "
                  "single complete run to keep", file=sys.stderr)
            return 1
        verdicts = prefix_verdicts(path, s, forced)
        for r in runs:
            if r.stamp != forced.stamp:
                print(f"  {r.stamp}  prefix of {forced.stamp}: {verdicts.get(r.stamp)}")
        if not all(verdicts.values()):
            print("verdict     : REFUSED — a shorter run is not an exact prefix of the "
                  "longest, so it holds rows the longest run does not; dropping it would "
                  "leave a hole", file=sys.stderr)
            return 1
        mode = "prefix"

    if s.n_unattributable and not args.drop_unattributable:
        print(f"verdict     : REFUSED — {s.n_unattributable:,} row(s) carry no usable "
              "ts_pull_utc and belong to no run; pass --drop-unattributable to drop them",
              file=sys.stderr)
        return 1

    if args.keep_pull:
        chosen = [r for r in runs if r.stamp == args.keep_pull]
        if not chosen:
            print(f"--keep-pull {args.keep_pull!r} is not one of "
                  f"{[r.stamp for r in runs]}", file=sys.stderr)
            return 3
        if forced is not None and chosen[0].stamp != forced.stamp:
            print(f"--keep-pull {args.keep_pull!r} names a run that is a PREFIX of "
                  f"{forced.stamp}; keeping it would drop rows only the longer run "
                  "holds", file=sys.stderr)
            return 3
        keep_run = chosen[0]
    else:
        keep_run = forced if forced is not None else runs[0]
    dropped_runs = [r for r in runs if r.stamp != keep_run.stamp]
    dropped = sum(r.rows for r in dropped_runs) + s.n_unattributable
    keep = keep_run.rows

    kind = "identical" if mode == "identical" else "prefix"
    print(f"repair      : {mode} runs — keep the run stamped {keep_run.stamp} "
          f"({keep:,} rows); drop {len(dropped_runs)} {kind} run(s) "
          f"({sum(r.rows for r in dropped_runs):,} rows) and "
          f"{s.n_unattributable:,} unattributable")
    if not args.apply:
        print("verdict     : dry run — pass --apply to write")
        return 0

    if s.total - dropped != keep:
        raise RepairError(f"arithmetic guard: {s.total:,} - {dropped:,} != {keep:,}")

    backup = None
    if not args.no_backup:
        backup = back_up(path, stamp_utc=utc_now_iso().replace(":", "").replace("-", ""))
        print(f"backup      : {backup}  ({backup.stat().st_size:,} bytes)")

    kept = rewrite_keeping_run(path, keep_run.stamp, expect_keep=keep)
    stamps = ", ".join(r.stamp for r in runs)
    if mode == "identical":
        how = (f"and wrote {keep_run.rows:,} identical rows each "
               f"(digest {keep_run.digest}); kept the run stamped {keep_run.stamp}")
    else:
        short = ", ".join(f"{r.stamp} {r.rows:,} rows" for r in dropped_runs)
        how = (f"and was cut off before finishing ({short}); each short run is an exact "
               f"prefix of the completed run {keep_run.stamp} ({keep_run.rows:,} rows, "
               f"digest {keep_run.digest}), which was kept")
    note = (f"repaired [{BEAD}]: the batch pull ran {len(runs)} times "
            f"(ts_pull_utc {stamps}) {how} and dropped "
            f"{sum(r.rows for r in dropped_runs):,} duplicate rows and "
            f"{s.n_unattributable:,} unattributable; {kept:,} rows remain")
    update_manifest_after_repair(d, args.stream, kept=kept, dropped=dropped - s.n_unattributable,
                                 unattributable=s.n_unattributable, keep_run=keep_run,
                                 dropped_runs=dropped_runs, note=note, mode=mode)
    print(f"verdict     : REPAIRED — {kept:,} rows kept, manifest cycles set")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RepairError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(3)
