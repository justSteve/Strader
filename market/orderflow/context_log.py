"""Live context log — what the page was shown BESIDES recognition. [st-2rsz]

WHY THIS EXISTS
    Fuel, GEX and the SPX→ES basis are display context: the feeder computes them
    AFTER the run log has recorded a bar's emissions and puts them on the page
    payload only (``fuel.py`` INTEGRATION CONTRACT). That keeps the run log a
    pure record of recognition, which is what live/replay parity diffs — and it
    also meant nothing durable held them. Once the bridge rolled to the next day,
    the Fuel line Steve read at 09:38 existed nowhere. The Emission Review
    lookback (st-rf95) needs exactly that line.

    So context gets its own file, written beside the run log, never inside it.
    The parity record is untouched by construction: different path, different
    writer, and the run log has already been written before any context exists.

FORMAT — ``data/derived/live-context/<day>.jsonl``, one object per line:

    {"k":"run", "day", "started"}                 one per feeder start
    {"k":"ctx", "i":N, "t1", "gex"?, "bs"?, "fuel"?}

A ``ctx`` row is written only when the bar carried some context; absent keys
mean "none on this bar", the same omit-when-unknown rule the payload uses.
Restarts append a fresh ``run`` header (as the run log does); readers take the
last run, whose bar indices match the last run of the run log.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "derived" / "live-context"


def context_log_path(day: _date) -> Path:
    return _ROOT / f"{day.isoformat()}.jsonl"


class ContextLogWriter:
    """Append one run's per-bar context. Never raises into the feeder — a disk
    error degrades to one warning and a dead writer, like ``RunLogWriter``."""

    live = True

    def __init__(self, path: Path, *, day: _date, started: datetime):
        self.path = path
        self._fh = None
        self.rows = 0
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("a", encoding="utf-8")
            self._write({"k": "run", "day": day.isoformat(), "started": started.isoformat()})
        except OSError as e:  # noqa: BLE001 — logging must not kill the feed
            logger.warning("context log unavailable at %s (%s) — continuing without it", path, e)
            self._fh = None

    def _write(self, rec: dict) -> None:
        if self._fh is None:
            return
        try:
            self._fh.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
            self._fh.flush()
        except (OSError, TypeError, ValueError) as e:  # noqa: BLE001
            logger.warning("context log write failed (%s) — disabling it for this run", e)
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None

    def on_bar(self, bar_i: int, bar, *, gex=None, bs=None, fuel=None) -> None:
        rec = {"k": "ctx", "i": bar_i, "t1": bar.end_ts.isoformat()}
        if gex:
            rec["gex"] = gex
        if bs and bs.get("pts") is not None:
            rec["bs"] = bs
        if fuel:
            rec["fuel"] = fuel
        if len(rec) > 3:
            self._write(rec)
            self.rows += 1

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


class NullContextLog:
    """No-op stand-in for ``--no-run-log`` / ``--dry-run`` and callers that pass none."""
    path = None
    live = False

    def on_bar(self, *a, **k) -> None: ...
    def close(self) -> None: ...


def read_last_run(path: Path) -> dict[int, dict]:
    """``{bar_i: ctx_row}`` for the last run in ``path`` (empty if absent)."""
    if not path.exists():
        return {}
    out: dict[int, dict] = {}
    for line in path.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("k") == "run":
            out = {}
        elif r.get("k") == "ctx" and isinstance(r.get("i"), int):
            out[r["i"]] = r
    return out
