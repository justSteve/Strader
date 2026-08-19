"""Live-run emission log — the record a replay gets diffed against. [st-x2mp]

WHY THIS EXISTS
    The live feeder drives the same ``StackDriver`` the replay path drives, so
    live == replay is true BY CONSTRUCTION (spec §5). It had never been
    MEASURED. The CI parity harness replays a committed fixture against a
    committed snapshot, which proves the pipeline is deterministic and has not
    silently changed — it says nothing about whether a live run of a real
    session agrees with a replay of that session's tape.

    Three seams can still separate them:

      1. Anchors. ``day_anchors`` needs the session high/low, which a replay
         knows at bar 0 and live cannot. ``LiveAnchors`` is the live rule, and
         it is a pure function of the bar stream — so a replay that drives
         LiveAnchors reproduces the live anchor set exactly, and this seam
         drops out of the diff. (The DRILL still has lookahead; that is a
         different comparison and not what this log is for.)
      2. The trailing partial bar. ``full_stack_events`` builds with
         ``include_partial=True``; the feeder renders closed bars only. The
         checker drives closed-bars-only for the same reason.
      3. Late rows. Replay sorts the whole file by (ts, sequence). Live holds
         rows for ``--reorder-lag`` seconds and releases in order, so a
         reconnect redelivering rows staler than that cannot be placed. If it
         ever happens, bar boundaries shift and every later index diverges.
         Nobody has measured whether it has. That is seam this log exists for.

FORMAT — one JSON object per line, four record kinds:

    {"k":"run",  ...}  run header: day, bar_n, mancini set, reorder lag, mode
    {"k":"bar",  "i":N, "t0","t1","o","h","l","c","v","d","nv"}
    {"k":"ev",   "i":N|null, <serialized signal fields>}
    {"k":"end",  "bars":N, "events":N}

A file accumulates RUNS, not sessions: restarting the feeder appends a fresh
``run`` header rather than truncating. That is deliberate — a restart is
exactly the kind of event worth still having the evidence of afterwards, and
truncating would destroy the run that was live when something went wrong.
``read_runs`` splits them back apart; an absent ``end`` marks a run that died
mid-session, which ``complete`` reports rather than hides.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date as _date, datetime
from pathlib import Path

from market.orderflow.anchors import kinds_from_records, kinds_to_records

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "derived" / "live-parity"


def run_log_path(day: _date) -> Path:
    """The canonical live-run log for ``day``. A NAME, not a promise."""
    return _ROOT / f"{day.isoformat()}.jsonl"


def bar_record(bar_i: int, bar) -> dict:
    """The bar identity fields the checker diffs.

    Deliberately NOT the whole footprint: cells and fill steps are rendering
    detail, and a diff that includes them reports a hundred lines of noise for
    one shifted boundary. Boundary (t0/t1/volume) plus OHLC and delta is what
    localises a divergence — if those agree, the cells agree, because both
    sides built them from the same trades with the same builder.
    """
    return {"k": "bar", "i": bar_i,
            "t0": bar.start_ts.isoformat(), "t1": bar.end_ts.isoformat(),
            "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
            "v": bar.volume, "d": bar.delta, "nv": bar.none_vol}


class RunLogWriter:
    """Append one run's bars and emissions. Never raises into the feeder.

    Capture and rendering are kept independent on purpose (see the feeder's
    header); this log is a third thing, and it is the LEAST important of the
    three. A disk error here must never take down a live session, so every
    write is guarded and a failure degrades to a warning and a dead writer.
    """

    def __init__(self, path: Path, *, day: _date, bar_n: int,
                 mancini: list[float], reorder_lag: float, catch_up: bool,
                 started: datetime, mancini_kinds=None):
        self.path = path
        self._fh = None
        self.bars = 0
        self.events = 0
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("a", encoding="utf-8")
            self._write({"k": "run", "day": day.isoformat(), "bar_n": bar_n,
                         "mancini": list(mancini),
                         # [[price, kind], ...] — which side each Mancini level
                         # is engaged from [st-tme]; the parity replay needs the
                         # same map or it watches a different anchor set
                         "mancini_kinds": kinds_to_records(mancini_kinds),
                         "reorder_lag": reorder_lag,
                         "catch_up": bool(catch_up),
                         "started": started.isoformat()})
        except OSError as e:  # noqa: BLE001 — logging must not kill capture
            logger.warning("run log unavailable at %s (%s) — continuing without it",
                           path, e)
            self._fh = None

    @property
    def live(self) -> bool:
        return self._fh is not None

    def _write(self, obj: dict) -> None:
        if self._fh is None:
            return
        try:
            self._fh.write(json.dumps(obj, separators=(",", ":")) + "\n")
            self._fh.flush()
        except (OSError, TypeError, ValueError) as e:  # noqa: BLE001
            logger.warning("run log write failed (%s) — disabling it", e)
            self.close(quiet=True)

    def on_bar(self, bar_i: int, bar, events: list[dict]) -> None:
        self._write(bar_record(bar_i, bar))
        self.bars += 1
        for e in events:
            self._write({"k": "ev"} | e)
            self.events += 1

    def on_final(self, events: list[dict]) -> None:
        for e in events:
            self._write({"k": "ev"} | e)
            self.events += 1

    def close(self, *, quiet: bool = False) -> None:
        if self._fh is None:
            return
        if not quiet:
            self._write({"k": "end", "bars": self.bars, "events": self.events})
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None


@dataclass
class Run:
    """One feeder run recovered from a log file."""

    meta: dict
    bars: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    complete: bool = False

    @property
    def started(self) -> str:
        return self.meta.get("started", "?")

    @property
    def bar_n(self) -> int:
        return int(self.meta.get("bar_n") or 0)

    @property
    def mancini(self) -> list[float]:
        return [float(x) for x in (self.meta.get("mancini") or [])]

    @property
    def mancini_kinds(self):
        """{price: kinds} the run anchored with; None for a log written
        before the header carried it (every level was a support then)."""
        return kinds_from_records(self.meta.get("mancini_kinds"))


def read_runs(path: Path) -> list[Run]:
    """Split a log file back into its runs, in file order.

    Unparseable lines are counted and skipped rather than fatal: a run killed
    mid-write leaves a torn last line, and losing the whole file to it would
    destroy exactly the evidence the torn line is a symptom of.
    """
    runs: list[Run] = []
    bad = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                kind = rec["k"]
            except (json.JSONDecodeError, KeyError, TypeError):
                bad += 1
                continue
            if kind == "run":
                runs.append(Run(meta=rec))
                continue
            if not runs:
                bad += 1  # records before any header belong to no run
                continue
            if kind == "bar":
                runs[-1].bars.append(rec)
            elif kind == "ev":
                runs[-1].events.append(rec)
            elif kind == "end":
                runs[-1].complete = True
    if bad:
        logger.warning("read_runs %s: %d unusable line(s) skipped", path.name, bad)
    return runs
