"""Replay-session recorder — the measured record of what the stack emitted. [st-055]

Runs the production full stack (NO parity fixture overrides) over one corpus
day and appends every emission to an append-only per-day JSONL under
``data/measurement/replay/``. The drill surface renders from the same
pipeline with the same anchor rule (market.orderflow.anchors), so what Steve
watched and what got recorded cannot diverge. The computation path holds zero
wall-clock reads, so this fast batch pass is byte-identical to a paced
"live" run over the same tape.

Record rows (one JSON object per line):
  RunMeta       — run_id, bead, git commit, bar_n, anchors, config snapshot
  DayType       — TPO Market-Profile day-type classification (tpo.py)
  <event rows>  — parity.serialize() fields + run (run_id), n (per-run
                  sequence), bar_i (completed-bar index; None for
                  end-of-stream flush and profile levels)

Append-only by design (the measured-record contract): writers use mode "a"
only; a re-run appends a new run block under a fresh run_id; no row is ever
modified or removed. Readers select the latest run (``read_latest_run``).
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import date as _date, datetime, timezone
from pathlib import Path
from typing import Iterable

import market.signals.orderflow_config as _config
from market.orderflow.anchors import Kinds, day_anchors, mancini_kinds_for, mancini_levels_for
from market.orderflow.bars import build_bars
from market.orderflow.parity import absorption_parity_run, full_stack_events
from market.orderflow.quotes import mbp1_day_path, read_mbp1_day
from market.orderflow.recognizer import Anchor
from market.orderflow.replay import read_corpus_day
from market.orderflow.tpo import build_tpo, classify_day_type

logger = logging.getLogger(__name__)

REPLAY_DIR = (Path(__file__).resolve().parent.parent.parent
              / "data" / "measurement" / "replay")


def signals_path(day: _date) -> Path:
    return REPLAY_DIR / f"signals_{day.isoformat()}.jsonl"


def annotations_path(day: _date) -> Path:
    return REPLAY_DIR / f"annotations_{day.isoformat()}.jsonl"


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _config_snapshot() -> dict:
    """Every UPPER_CASE scalar in orderflow_config — the thresholds this run
    actually ran under, frozen into the record."""
    return {k: v for k, v in vars(_config).items()
            if k.isupper() and isinstance(v, (int, float, str))}


def record_day(day: _date | Path, *, bar_n: int = _config.VOLUME_BAR_N,
               anchors: list[Anchor] | None = None,
               mancini_prices: Iterable[float] | None = None,
               mancini_kinds: Kinds | None = None,
               book_path: Path | None = None,
               out_path: Path | None = None) -> dict:
    """Run the production stack over one day and append the record.

    ``day`` may be a fixture Path (tests). When ``anchors`` is None they are
    derived by the shared rule: the day's Mancini levels of their parsed kind
    (``mancini_kinds_for``; or the explicit ``mancini_prices`` override with
    ``mancini_kinds``, bare prices = supports) plus session range edges
    [st-tme]. Absorption: for a
    real date the day's MBP-1 file is auto-detected (``mbp1_day_path``); for a
    fixture Path pass ``book_path`` explicitly. Days without book data record
    trades-only, flagged ``mbp1: false`` in RunMeta. Returns the RunMeta dict
    with ``n_events``, ``day_type`` and ``path`` added.
    """
    trades = read_corpus_day(day)
    if not trades:
        raise ValueError(f"replay day {day} parsed to zero trades")
    day_d = trades[0].ts.date()
    bars = list(build_bars(iter(trades), n=bar_n, include_partial=True))

    if mancini_prices is not None:
        mancini = sorted(float(x) for x in mancini_prices)
    elif anchors is not None:
        mancini = sorted(a.price for a in anchors if a.mancini)
    else:
        mancini = mancini_levels_for(day_d)
        if mancini_kinds is None:
            mancini_kinds = mancini_kinds_for(day_d)
    if anchors is None:
        anchors = day_anchors(mancini, max(b.high for b in bars),
                              min(b.low for b in bars), mancini_kinds)

    events = full_stack_events(trades, bar_n=bar_n, anchors=anchors,
                               mancini_prices=mancini)

    book = book_path if book_path is not None else (
        mbp1_day_path(day_d) if not isinstance(day, Path) else None)
    has_book = book is not None and Path(book).exists()
    if has_book:
        events += [e | {"bar_i": None}
                   for e in absorption_parity_run(read_mbp1_day(Path(book)))]

    try:
        day_type, why = classify_day_type(build_tpo(trades))
    except Exception as exc:  # classification must not sink the record
        day_type, why = "unknown", f"classify failed: {exc}"

    now = datetime.now(timezone.utc)
    run_id = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{_git_head()}"
    meta = {"type": "RunMeta", "run": run_id, "n": 0, "bead": "st-055",
            "date": day_d.isoformat(), "bar_n": bar_n,
            "n_trades": len(trades), "n_bars": len(bars),
            "anchors": [[a.price, a.kind, a.label, a.mancini] for a in anchors],
            "mancini": mancini, "mbp1": has_book, "git": _git_head(),
            "config": _config_snapshot(),
            "logged_utc": now.isoformat(timespec="seconds")}

    path = out_path or signals_path(day_d)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:  # append-only: "a", never "w"
        f.write(json.dumps(meta, separators=(",", ":")) + "\n")
        f.write(json.dumps({"type": "DayType", "run": run_id, "n": 1,
                            "day_type": day_type, "why": why},
                           separators=(",", ":")) + "\n")
        for i, e in enumerate(events, start=2):
            f.write(json.dumps({"run": run_id, "n": i} | e,
                               separators=(",", ":")) + "\n")
    logger.info("record_day %s: %d trades -> %d events -> %s (run %s)",
                day_d, len(trades), len(events), path, run_id)
    return meta | {"n_events": len(events), "day_type": day_type,
                   "path": str(path)}


def read_latest_run(path: Path) -> list[dict]:
    """Rows of the most recent run block in an append-only record file."""
    rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    if not rows:
        return []
    last = rows[-1]["run"]
    return [r for r in rows if r["run"] == last]
