# FootPrint Replay Drills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replay each day of an imported DataBento RTH week through the production classifier/recognizer stack as-if-live, with every emission recorded per day in an append-only measured record that Steve reviews — from his seat, on the same FootPrint surface — with 20/20 hindsight annotations.

**Bead:** st-055 (FootPrint Replay Drills)

**Architecture:** The entire computation path (`read_corpus_day → build_bars → OrderflowEngine → find_stacks → SetupRecognizer`) contains **zero wall-clock reads** (verified 2026-07-25 by grep over `market/`, `strader/`, `scripts/` — all time is event time from `provenance.ts_event`; the only pacing in the system is browser `setTimeout` at `scripts/orderflow_drill_template.html:547`). Therefore recording and watching decouple with no fidelity loss: a fast deterministic batch pass writes the measured record, and Steve watches the *identical* pipeline through the existing drill HTML at speed 1× — same bars, same anchors, same recognizer, so the record and the surface cannot diverge. No Python wall-time driver is needed; building one would add machinery without changing a single recorded byte.

**Tech Stack:** Python ≥3.11 stdlib-only (repo core convention), pytest, existing modules `market/orderflow/{replay,bars,engine,imbalance,recognizer,parity,tpo}.py`, existing drill surface `scripts/orderflow_drill.py` + template.

**Target week:** 2026-07-13 → 2026-07-17 (most recent complete Mon–Fri full-RTH week; 2026-07-24 ES tape is missing so the 07-20 week has only 4 days). The 2026-07-06 → 07-10 week is also complete and replayable with the same tooling.

**Explicitly out of scope (deferred, do not build):**
- `DayTypeClassifier` (playbook) binding — it takes declared `MarketPrimitives`, not feeds; binding is deferred per co-wh19 §10. Per-day classification here uses the computable TPO classifier (`market/orderflow/tpo.py:classify_day_type`).
- ~~Absorption — needs MBP-1, which exists only for 2026-07-02~~ **AMENDED 2026-07-25 (st-ve6 backfill): MBP-1 now exists for 07-02, 07-13→17, 07-20→22. Absorption IS in scope**: the recorder auto-detects the day's MBP-1 file and appends `absorption_parity_run` emissions (production floors, no overrides) to the same record. Days without MBP-1 (07-23, 07-24 pending billing; the 07-06 week) record trades-only, flagged in RunMeta.
- Live GLBX feed / live footprint renderer — Phase B (2026-08-01, orderflow-signal-layer-design §Phase B).

**Invariants (bead constraints):**
- Replay NEVER touches live data paths: corpus files are opened read-only; the recorder writes only under `data/measurement/replay/` (gitignored, like all measured data records); drill HTML goes to `/tmp/`. No Schwab, no DataBento pulls, no `data/corpus/` writes.
- All record files are append-only: writers open with mode `"a"` only; a re-run appends a new run block under a fresh `run_id`; no row is ever modified or removed. Readers select the latest run.

**New files:**

| File | Responsibility |
|---|---|
| `market/orderflow/anchors.py` | Single source for day-anchor derivation (Mancini levels + session range edges) shared by drill and recorder |
| `market/orderflow/session_record.py` | The recorder: production-floor full-stack run → append-only per-day JSONL |
| `scripts/replay_day.py` | One-command drill-day launcher: record + generate drill HTML + open browser |
| `scripts/replay_annotate.py` | Append-only hindsight annotations (Steve dictates, agent appends) |
| `scripts/replay_review.py` | Hindsight review page: latest run + annotations → self-contained HTML |
| `docs/drills/replay-week-workflow.md` | The drill workflow from Steve's seat |
| `tests/market/orderflow/test_anchors.py`, `tests/market/orderflow/test_session_record.py`, `tests/scripts/test_replay_annotate.py`, `tests/scripts/test_replay_review.py` | Tests |

**Modified files:**

| File | Change |
|---|---|
| `scripts/orderflow_drill.py` | `mancini_levels_for` + anchor assembly move to `market/orderflow/anchors.py`; drill imports them (behavior unchanged) |
| `market/orderflow/parity.py` | Drive loop extracted as `full_stack_events(...)`; `parity_run` wraps it with fixture overrides (snapshot must not change) |

**Test commands:** always `.venv/bin/python -m pytest ...` (system `python3` hits collection errors; only `python3 -m pytest *` is auto-allowed for the agent — both work for the suites named below).

---

### Task 1: Shared anchor derivation — `market/orderflow/anchors.py`

The recognizer's output depends on its anchors. Today the anchor rule (day's Mancini levels as `support`, plus session range edges) lives inline in `scripts/orderflow_drill.py:build_anatomy` and `mancini_levels_for`. The recorder must use the SAME rule or the record won't match the surface Steve watched. Extract it.

**Files:**
- Create: `market/orderflow/anchors.py`
- Modify: `scripts/orderflow_drill.py` (lines 42–44 constants, 79–94 `mancini_levels_for`, 97–122 `build_anatomy`)
- Test: `tests/market/orderflow/test_anchors.py`

- [ ] **Step 1: Write the failing test**

```python
"""Anchor-derivation rule tests. [st-055]"""
from datetime import date

from market.orderflow.anchors import day_anchors, mancini_levels_for


def test_day_anchors_mancini_plus_range_edges():
    a = day_anchors([6212.0, 6230.0], 6250.0, 6200.0)
    assert [(x.price, x.kind, x.mancini) for x in a] == [
        (6212.0, "support", True),
        (6230.0, "support", True),
        (6250.0, "range_high", False),
        (6200.0, "range_low", False),
    ]


def test_day_anchors_dedup_on_price_and_kind():
    # duplicate mancini level collapses; a level equal to the session low is a
    # different KIND, so both survive
    a = day_anchors([6200.0, 6200.0], 6250.0, 6200.0)
    assert len(a) == 3
    kinds = {x.kind for x in a}
    assert kinds == {"support", "range_high", "range_low"}


def test_mancini_levels_for_unlabeled_day_is_empty():
    assert mancini_levels_for(date(1999, 1, 1)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_anchors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'market.orderflow.anchors'`

- [ ] **Step 3: Create `market/orderflow/anchors.py`**

```python
"""Day-anchor derivation — the one rule for what the recognizer watches. [st-055]

Both the drill surface (scripts/orderflow_drill.py) and the replay recorder
(market/orderflow/session_record.py) must run the recognizer against the SAME
anchor set, or the record Steve reviews will not match the surface he watched.
This module owns that rule: the day's Mancini levels (the validated anchor
source, st-3vu) as ``support`` anchors, plus the session range edges so
unlabeled days still surface ``range_trap`` recognitions.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date
from pathlib import Path

from market.orderflow.recognizer import Anchor

logger = logging.getLogger(__name__)

LABELS = (Path(__file__).resolve().parent.parent.parent
          / "docs/measurement/mancini-setup-labels-2026-07-06.json")
FAMILY = {"failed_breakdown", "level_reclaim"}


def mancini_levels_for(day: _date) -> list[float]:
    """The day's Mancini support/resistance levels from the labeled corpus —
    the same anchor source score_recognizer.py validated against. Empty for
    unlabeled days (callers then fall back to session range edges)."""
    if not LABELS.exists():
        return []
    try:
        entries = json.loads(LABELS.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("could not read Mancini labels (%s); using range edges only", e)
        return []
    lv = {round(float(x), 2)
          for e in entries
          if e.get("session_date") == day.isoformat() and e.get("setup") in FAMILY
          for x in e.get("es_levels", []) if 5000 < float(x) < 9000}
    return sorted(lv)


def day_anchors(mancini_levels: list[float], session_high: float,
                session_low: float) -> list[Anchor]:
    """Mancini levels as support anchors plus the session range edges,
    deduped on (price, kind)."""
    anchors: list[Anchor] = []
    seen: set[tuple[float, str]] = set()

    def add(price: float, kind: str, label: str, mancini: bool = False) -> None:
        key = (round(price, 2), kind)
        if key in seen:
            return
        seen.add(key)
        anchors.append(Anchor(price, kind, label, mancini=mancini))

    for lv in mancini_levels:
        add(lv, "support", f"mancini {lv:g}", mancini=True)
    add(session_high, "range_high", "day high")
    add(session_low, "range_low", "day low")
    return anchors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_anchors.py -v`
Expected: 3 PASS

- [ ] **Step 5: Point the drill at the shared module**

In `scripts/orderflow_drill.py`:

1. Add to the imports block (after the `anatomy_payload` import at line 36):

```python
from market.orderflow.anchors import day_anchors, mancini_levels_for  # noqa: E402
```

2. Delete the module constants `LABELS` and `FAMILY` (lines 42–44 — keep `DECK`) and delete the whole local `mancini_levels_for` function (lines 79–94).

3. Replace the body of `build_anatomy` (keep its signature and docstring) so the anchor assembly uses the shared rule:

```python
def build_anatomy(bars: list, suggested: dict, mancini_levels: list[float]) -> list[dict]:
    """Run the validated recognizer over the day and fold its emissions into
    four-stage walkthrough instances (st-yfn anatomy mode). Anchors come from
    market.orderflow.anchors.day_anchors — the same rule the replay recorder
    uses (st-055), so drill anatomy and the measured record cannot diverge."""
    anchors = day_anchors(mancini_levels,
                          suggested["session_high"], suggested["session_low"])
    if not anchors:
        return []
    recs = SetupRecognizer(anchors, mancini_prices=mancini_levels).run(bars)
    instances = build_instances(recs, bars)
    logger.info("anatomy: %d anchors -> %d recs -> %d instances",
                len(anchors), len(recs), len(instances))
    return anatomy_payload(instances)
```

- [ ] **Step 6: Run the orderflow + scripts suites to prove no drift**

Run: `.venv/bin/python -m pytest tests/market/orderflow tests/scripts -q`
Expected: all PASS (the parity snapshot test is the behavioral guard)

- [ ] **Step 7: Commit**

```bash
git add market/orderflow/anchors.py scripts/orderflow_drill.py tests/market/orderflow/test_anchors.py
git commit -m "refactor(orderflow): extract shared day-anchor rule to anchors.py [st-055]"
```

---

### Task 2: Extract the full-stack drive loop from parity

`parity_run` (`market/orderflow/parity.py:98-137`) already drives reader-ordered trades → bars → engine-per-trade → stacks-per-bar → recognizer-per-bar → profile levels in one deterministic pass — but it hard-wires fixture-scale threshold overrides and fixture anchors. Extract the loop as `full_stack_events(...)` running at *current module thresholds* with caller-supplied anchors, and make `parity_run` a thin wrapper. The committed parity snapshot must not change.

**Files:**
- Modify: `market/orderflow/parity.py:98-137`
- Test: `tests/market/orderflow/test_parity_harness.py` (existing, unchanged — it IS the no-drift proof) + new structural test appended to `tests/market/orderflow/test_anchors.py`? No — put it in the new file `tests/market/orderflow/test_session_record.py` created in Task 3. For THIS task the existing parity test suffices.

- [ ] **Step 1: Replace `parity_run` in `market/orderflow/parity.py`**

Replace the whole `parity_run` function (lines 98–137) with:

```python
def full_stack_events(trades: list[Trade], *, bar_n: int,
                      anchors: Iterable[Anchor],
                      mancini_prices: Iterable[float] = ()) -> list[dict]:
    """One deterministic pass of the full stack at CURRENT module thresholds.

    The canonical drive loop (ordering rules in the module docstring), shared
    by the parity harness (fixture floors via ``_overridden``) and the replay
    recorder (production floors, st-055). Every event dict carries ``bar_i``
    — the index of the completed bar it was emitted under, ``None`` for
    end-of-stream flush signals and profile levels.
    """
    events: list[dict] = []
    engine = OrderflowEngine()
    recognizer = SetupRecognizer(list(anchors), mancini_prices=list(mancini_prices))

    idx = 0
    # Drive engine per-trade and bar-consumers per-bar in one pass: bars close
    # on known trade boundaries, so process trades until each bar's volume is
    # covered — same faithful drive as the live adapter would produce.
    for bar_i, bar in enumerate(build_bars(iter(trades), n=bar_n, include_partial=True)):
        vol = 0
        while idx < len(trades) and vol < bar.volume:
            t = trades[idx]
            for s in engine.process(t):
                events.append(serialize(s) | {"bar_i": bar_i})
            vol += t.size
            idx += 1
        for stack in find_stacks(bar):
            events.append(serialize(stack) | {"bar_i": bar_i})
        for rec in recognizer.on_bar(bar):
            events.append(serialize(rec) | {"bar_i": bar_i})
    while idx < len(trades):
        for s in engine.process(trades[idx]):
            events.append(serialize(s) | {"bar_i": None})
        idx += 1
    for s in engine.flush():
        events.append(serialize(s) | {"bar_i": None})

    prof = build_profile(trades)
    for lv in profile_levels(prof, reference_price=trades[-1].price):
        events.append(serialize(lv) | {"bar_i": None})
    return events


def parity_run(trades: Iterable[Trade]) -> list[dict]:
    """The canonical full-stack replay. Deterministic: same trades, same list."""
    trades = list(trades)
    with _overridden():
        events = full_stack_events(trades, bar_n=PARITY_BAR_N,
                                   anchors=PARITY_ANCHORS,
                                   mancini_prices=PARITY_MANCINI)
    for e in events:
        e.pop("bar_i", None)  # snapshot format predates bar_i; keep it stable
    logger.info("parity_run: %d trades -> %d events", len(trades), len(events))
    return events
```

(The unused `pending: list[Trade] = []` from the old body is dropped; `absorption_parity_run` and everything above line 98 stay untouched.)

- [ ] **Step 2: Run the parity harness to prove the snapshot is unchanged**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_parity_harness.py tests/market/orderflow/test_replay_golden.py -v`
Expected: all PASS with zero snapshot diffs. If ANY parity field differs, the refactor is wrong — fix the loop, do NOT regenerate the snapshot.

- [ ] **Step 3: Run the full orderflow suite**

Run: `.venv/bin/python -m pytest tests/market/orderflow -q`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add market/orderflow/parity.py
git commit -m "refactor(orderflow): extract full_stack_events drive loop from parity_run [st-055]"
```

---

### Task 3: The recorder — `market/orderflow/session_record.py`

**Files:**
- Create: `market/orderflow/session_record.py`
- Test: `tests/market/orderflow/test_session_record.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Replay-session recorder tests. [st-055]

Uses the committed golden tape (the parity fixture day) — no corpus
dependency, so these run in CI.
"""
import json
from pathlib import Path

import market.signals.orderflow_config as orderflow_config
from market.orderflow.recognizer import Anchor
from market.orderflow.session_record import read_latest_run, record_day

FIXTURE = Path(__file__).resolve().parent.parent.parent \
    / "market/fixtures/es_ticks_golden_20260702.jsonl"
ANCHORS = [Anchor(7482.0, "support", "poc"), Anchor(7555.0, "resistance", "am")]


def _record(out):
    return record_day(FIXTURE, anchors=list(ANCHORS), mancini_prices=[7482.5],
                      out_path=out)


def test_record_rows_structure(tmp_path):
    out = tmp_path / "signals_test.jsonl"
    meta = _record(out)
    rows = [json.loads(l) for l in out.open()]
    assert rows[0]["type"] == "RunMeta" and rows[0]["n"] == 0
    assert rows[0]["bead"] == "st-055"
    assert rows[1]["type"] == "DayType" and rows[1]["n"] == 1
    ns = [r["n"] for r in rows]
    assert ns == sorted(ns) and len(set(ns)) == len(ns)
    assert all("bar_i" in r for r in rows[2:])
    assert all(r["run"] == meta["run"] for r in rows)
    # production floors, not parity fixture floors
    assert rows[0]["config"]["FLUSH_DELTA_MIN"] == orderflow_config.FLUSH_DELTA_MIN == 300
    assert meta["n_events"] == len(rows) - 2


def test_record_is_append_only_and_deterministic(tmp_path):
    out = tmp_path / "signals_test.jsonl"
    m1 = _record(out)
    first_block = out.read_text()
    m2 = _record(out)
    assert m1["run"] != m2["run"]
    # append-only: the first run's bytes are still there, untouched, in front
    assert out.read_text().startswith(first_block)
    rows = [json.loads(l) for l in out.open()]

    def strip(r):
        return {k: v for k, v in r.items() if k not in ("run", "logged_utc", "git")}

    r1 = [strip(r) for r in rows if r["run"] == m1["run"]]
    r2 = [strip(r) for r in rows if r["run"] == m2["run"]]
    assert r1 == r2  # same tape + same anchors + same code = same record


def test_read_latest_run_selects_last_block(tmp_path):
    out = tmp_path / "signals_test.jsonl"
    _record(out)
    m2 = _record(out)
    latest = read_latest_run(out)
    assert latest and all(r["run"] == m2["run"] for r in latest)
    assert latest[0]["type"] == "RunMeta"


MBP1_FIXTURE = Path(__file__).resolve().parent.parent.parent \
    / "market/fixtures/es_mbp1_golden_20260702.jsonl.gz"


def test_record_includes_absorption_when_book_present(tmp_path):
    without = tmp_path / "without.jsonl"
    with_book = tmp_path / "with.jsonl"
    m0 = record_day(FIXTURE, anchors=list(ANCHORS), out_path=without)
    m1 = record_day(FIXTURE, anchors=list(ANCHORS), out_path=with_book,
                    book_path=MBP1_FIXTURE)
    assert m0["mbp1"] is False and m1["mbp1"] is True
    assert m1["n_events"] > m0["n_events"]  # absorption reads appended
    rows = [json.loads(l) for l in with_book.open()]
    assert all("bar_i" in r for r in rows[2:])  # absorption rows carry bar_i=None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_session_record.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'market.orderflow.session_record'`

- [ ] **Step 3: Create `market/orderflow/session_record.py`**

```python
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
from market.orderflow.anchors import day_anchors, mancini_levels_for
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
               book_path: Path | None = None,
               out_path: Path | None = None) -> dict:
    """Run the production stack over one day and append the record.

    ``day`` may be a fixture Path (tests). When ``anchors`` is None they are
    derived by the shared rule: the day's Mancini levels (or the explicit
    ``mancini_prices`` override) plus session range edges. Absorption: for a
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
    if anchors is None:
        anchors = day_anchors(mancini, max(b.high for b in bars),
                              min(b.low for b in bars))

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_session_record.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add market/orderflow/session_record.py tests/market/orderflow/test_session_record.py
git commit -m "feat(orderflow): replay-session recorder — append-only measured record per day [st-055]"
```

---

### Task 4: The launcher — `scripts/replay_day.py`

**Files:**
- Create: `scripts/replay_day.py`

- [ ] **Step 1: Create `scripts/replay_day.py`**

```python
#!/usr/bin/env python3
"""FootPrint replay drill launcher — one corpus day, as-if-live. [st-055]

One command per drill day:
  1. RECORD  — run the production classifier/recognizer stack over the day's
     tape and append the measured record (session_record.record_day).
  2. SURFACE — generate the footprint drill HTML via the same
     bars_payload/render path as scripts/orderflow_drill.py (identical
     surface, identical anchor rule) and open it in the Windows browser.
     Watch at speed 1x for as-if-live pacing.

The computation path holds zero wall-clock reads (st-055 plan), so the
record is byte-identical to what a live session over the same tape would
emit — recording fast and watching paced are the same measurement.

Usage:
    .venv/bin/python scripts/replay_day.py --date 2026-07-13
    .venv/bin/python scripts/replay_day.py --date 2026-07-13 --record-only
    .venv/bin/python scripts/replay_day.py --date 2026-07-13 --mancini-levels 6212,6230
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.session_record import record_day            # noqa: E402
from market.signals.orderflow_config import VOLUME_BAR_N          # noqa: E402
from scripts.orderflow_drill import bars_payload, open_in_browser, render  # noqa: E402

logger = logging.getLogger("replay_day")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Launch a FootPrint replay drill day [st-055]")
    ap.add_argument("--date", required=True, help="Corpus day YYYY-MM-DD")
    ap.add_argument("--bar-n", type=int, default=VOLUME_BAR_N,
                    help=f"Contracts per bar (default {VOLUME_BAR_N})")
    ap.add_argument("--mancini-levels", help="Comma-separated ES levels to anchor "
                    "BOTH the record and the drill (overrides the labeled-corpus "
                    "lookup; e.g. 6212,6230)")
    ap.add_argument("--record-only", action="store_true",
                    help="Write the measured record; skip the drill HTML")
    ap.add_argument("--no-open", action="store_true", help="Skip auto-opening the browser")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date)
    mancini = ([float(x) for x in args.mancini_levels.split(",") if x.strip()]
               if args.mancini_levels else None)

    meta = record_day(day, bar_n=args.bar_n, mancini_prices=mancini)
    print(f"recorded: run {meta['run']} — {meta['n_events']} events "
          f"({meta['day_type']} day) -> {meta['path']}")
    if args.record_only:
        return 0

    out = Path(f"/tmp/desk-orderflow-drill-{day.isoformat()}.html")
    payload = bars_payload(day, args.bar_n, mancini_levels=mancini)
    render(payload, out)
    if not args.no_open:
        open_in_browser(out)
    print(f"drill ready: {out}  ({payload['meta']['n_bars']} bars, "
          f"{payload['meta']['contracts']:,} contracts) — set speed 1x for as-if-live")
    print(f"annotate:  .venv/bin/python scripts/replay_annotate.py --date {day.isoformat()} "
          f"--time HH:MM --text \"...\"")
    print(f"review:    .venv/bin/python scripts/replay_review.py --date {day.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify against the real corpus (2026-07-02 exists on disk)**

Run: `.venv/bin/python scripts/replay_day.py --date 2026-07-02 --record-only`
Expected: `recorded: run <stamp>-<hash> — <N> events (<type> day) -> .../data/measurement/replay/signals_2026-07-02.jsonl` with N > 0. (07-02 is the out-of-order/dupes day — `read_corpus_day` canonicalizes it; a clean pass here exercises the whole read path.)

- [ ] **Step 3: Verify the record file**

Run: `head -2 data/measurement/replay/signals_2026-07-02.jsonl | .venv/bin/python -m json.tool --json-lines | head -30`
Expected: first row `"type": "RunMeta"` with anchors + config; second row `"type": "DayType"`.

- [ ] **Step 4: Commit**

```bash
git add scripts/replay_day.py
git commit -m "feat(scripts): replay_day launcher — record + drill surface in one command [st-055]"
```

---

### Task 5: Hindsight annotations — `scripts/replay_annotate.py`

Steve dictates; the agent runs the keystrokes (dictation-model convention). Annotations land append-only next to the day's signal record, keyed by CT event time and/or bar index.

**Files:**
- Create: `scripts/replay_annotate.py`
- Test: `tests/scripts/test_replay_annotate.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Hindsight-annotation append/read tests. [st-055]"""
from datetime import date

import pytest

from scripts.replay_annotate import append_annotation, read_annotations

DAY = date(2026, 7, 13)


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "annotations_test.jsonl"
    append_annotation(DAY, "flush into 6212 was the real one", time_ct="09:14", path=p)
    append_annotation(DAY, "chop after lunch, recognizer rightly quiet", bar_i=140, path=p)
    rows = read_annotations(DAY, path=p)
    assert [r["text"] for r in rows] == [
        "flush into 6212 was the real one",
        "chop after lunch, recognizer rightly quiet",
    ]
    assert rows[0]["time_ct"] == "09:14" and rows[0]["bar_i"] is None
    assert rows[1]["bar_i"] == 140 and rows[1]["time_ct"] is None
    assert all(r["type"] == "Annotation" and r["date"] == "2026-07-13" for r in rows)


def test_append_is_append_only(tmp_path):
    p = tmp_path / "annotations_test.jsonl"
    append_annotation(DAY, "first", path=p)
    before = p.read_text()
    append_annotation(DAY, "second", path=p)
    assert p.read_text().startswith(before)


def test_rejects_empty_text_and_bad_time(tmp_path):
    p = tmp_path / "annotations_test.jsonl"
    with pytest.raises(ValueError):
        append_annotation(DAY, "   ", path=p)
    with pytest.raises(ValueError):
        append_annotation(DAY, "note", time_ct="25:99", path=p)
    assert not p.exists()


def test_read_missing_file_is_empty(tmp_path):
    assert read_annotations(DAY, path=tmp_path / "nope.jsonl") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/scripts/test_replay_annotate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.replay_annotate'`

- [ ] **Step 3: Create `scripts/replay_annotate.py`**

```python
#!/usr/bin/env python3
"""Hindsight annotations for replayed days — append-only. [st-055]

Steve dictates; the agent appends. Each annotation is one JSONL row next to
the day's signal record (data/measurement/replay/annotations_<date>.jsonl),
keyed to CT event time (--time) and/or bar index (--bar). Never rewritten.

Usage:
    .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 \
        --time 09:14 --text "flush into 6212 was the real one"
    .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 --bar 140 \
        --text "chop after lunch, recognizer rightly quiet"
    .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 --list
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.session_record import annotations_path  # noqa: E402


def append_annotation(day: _date, text: str, *, time_ct: str | None = None,
                      bar_i: int | None = None, path: Path | None = None) -> dict:
    if not text.strip():
        raise ValueError("annotation text is empty")
    if time_ct is not None:
        try:
            datetime.strptime(time_ct, "%H:%M")
        except ValueError as e:
            raise ValueError(f"--time must be HH:MM CT ({time_ct!r})") from e
    row = {"type": "Annotation", "date": day.isoformat(),
           "time_ct": time_ct, "bar_i": bar_i, "text": text.strip(),
           "logged_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    p = path or annotations_path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:  # append-only: "a", never "w"
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row


def read_annotations(day: _date, path: Path | None = None) -> list[dict]:
    p = path or annotations_path(day)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


def _where(r: dict) -> str:
    if r.get("time_ct"):
        return f"{r['time_ct']} CT"
    if r.get("bar_i") is not None:
        return f"bar {r['bar_i']}"
    return "day"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Append a hindsight annotation [st-055]")
    ap.add_argument("--date", required=True, help="Replayed day YYYY-MM-DD")
    ap.add_argument("--text", help="The annotation (required unless --list)")
    ap.add_argument("--time", help="CT event time HH:MM the note refers to")
    ap.add_argument("--bar", type=int, help="Bar index the note refers to")
    ap.add_argument("--list", action="store_true", help="Print the day's annotations")
    args = ap.parse_args(argv)

    day = _date.fromisoformat(args.date)
    if args.list:
        for r in read_annotations(day):
            print(f"[{_where(r)}] {r['text']}")
        return 0
    if not args.text:
        ap.error("--text is required unless --list")
    row = append_annotation(day, args.text, time_ct=args.time, bar_i=args.bar)
    print(f"noted [{_where(row)}] {row['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/scripts/test_replay_annotate.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/replay_annotate.py tests/scripts/test_replay_annotate.py
git commit -m "feat(scripts): append-only hindsight annotations for replay days [st-055]"
```

---

### Task 6: The review page — `scripts/replay_review.py`

Merges the latest recorded run with the day's annotations into one self-contained HTML page, opened in the Windows browser (same `open_in_browser` mechanism as the drill).

**Files:**
- Create: `scripts/replay_review.py`
- Test: `tests/scripts/test_replay_review.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Review-payload merge tests. [st-055]"""
from scripts.replay_review import review_payload

ROWS = [
    {"type": "RunMeta", "run": "r2", "n": 0, "date": "2026-07-13",
     "n_trades": 1000, "n_bars": 12, "bar_n": 2000},
    {"type": "DayType", "run": "r2", "n": 1, "day_type": "trend", "why": "one-timeframing"},
    {"type": "SweepPrint", "run": "r2", "n": 2, "bar_i": 3},
    {"type": "SetupRecognition", "run": "r2", "n": 3, "bar_i": 5,
     "setup": "failed_breakdown", "bias": "bullish", "anchor_price": 6212.0,
     "state": "forming", "beats": ["flush"], "timestamp": "2026-07-13T09:12:04-05:00"},
    {"type": "SetupRecognition", "run": "r2", "n": 4, "bar_i": 7,
     "setup": "failed_breakdown", "bias": "bullish", "anchor_price": 6212.0,
     "state": "confirmed", "beats": ["flush", "stall", "flip", "confirm"],
     "timestamp": "2026-07-13T09:31:40-05:00"},
]
ANNS = [{"type": "Annotation", "date": "2026-07-13", "time_ct": "09:14",
         "bar_i": None, "text": "the real one"}]


def test_review_payload_splits_and_counts():
    p = review_payload(ROWS, ANNS)
    assert p["meta"]["run"] == "r2"
    assert p["day_type"]["day_type"] == "trend"
    assert p["counts"] == {"SweepPrint": 1, "SetupRecognition": 2}
    assert len(p["recognitions"]) == 2
    assert len(p["confirmed"]) == 1 and p["confirmed"][0]["state"] == "confirmed"
    assert p["annotations"] == ANNS


def test_review_payload_empty_inputs():
    p = review_payload([], [])
    assert p["meta"] == {} and p["counts"] == {} and p["confirmed"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/scripts/test_replay_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.replay_review'`

- [ ] **Step 3: Create `scripts/replay_review.py`**

```python
#!/usr/bin/env python3
"""Hindsight review page for a replayed day. [st-055]

Reads the LATEST recorded run (data/measurement/replay/signals_<date>.jsonl)
plus the day's annotations and renders one self-contained HTML page:
day type, every recognition with its stages, emission counts, and Steve's
hindsight notes — the 20/20 record to audit the recognizer against.

Usage:
    .venv/bin/python scripts/replay_review.py --date 2026-07-13
    .venv/bin/python scripts/replay_review.py --date 2026-07-13 --no-open
"""
from __future__ import annotations

import argparse
import html as _html
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.session_record import (annotations_path,        # noqa: E402
                                             read_latest_run, signals_path)
from scripts.orderflow_drill import open_in_browser                   # noqa: E402
from scripts.replay_annotate import read_annotations                  # noqa: E402

logger = logging.getLogger("replay_review")


def review_payload(rows: list[dict], annotations: list[dict]) -> dict:
    """Latest-run record rows + annotation rows -> one review dict."""
    meta = next((r for r in rows if r.get("type") == "RunMeta"), {})
    day_type = next((r for r in rows if r.get("type") == "DayType"), {})
    events = [r for r in rows if r.get("type") not in ("RunMeta", "DayType")]
    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    recs = [e for e in events if e["type"] == "SetupRecognition"]
    return {"meta": meta, "day_type": day_type, "counts": counts,
            "recognitions": recs,
            "confirmed": [r for r in recs if r.get("state") == "confirmed"],
            "annotations": annotations}


def render_html(p: dict) -> str:
    def esc(x) -> str:
        return _html.escape(str(x))

    def _ann_where(a: dict) -> str:
        if a.get("time_ct"):
            return f"{a['time_ct']} CT"
        if a.get("bar_i") is not None:
            return f"bar {a['bar_i']}"
        return "day"

    meta, dt = p["meta"], p["day_type"]
    rec_rows = "".join(
        f"<tr><td>{esc(r.get('timestamp', ''))[11:19]}</td><td>{esc(r.get('setup', ''))}</td>"
        f"<td>{esc(r.get('bias', ''))}</td><td>{esc(r.get('anchor_price', ''))}</td>"
        f"<td>{esc(r.get('state', ''))}</td>"
        f"<td>{esc(' > '.join(r.get('beats', [])))}</td>"
        f"<td>{esc(r.get('bar_i', ''))}</td></tr>"
        for r in p["recognitions"])
    ann_rows = "".join(
        f"<tr><td>{esc(_ann_where(a))}</td><td>{esc(a.get('text', ''))}</td></tr>"
        for a in p["annotations"])
    count_rows = "".join(f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
                         for k, v in sorted(p["counts"].items()))
    return f"""<!doctype html><meta charset="utf-8">
<title>Replay review {esc(meta.get('date', ''))}</title>
<style>
body{{font:14px/1.5 system-ui;margin:2rem;max-width:70rem}}
table{{border-collapse:collapse;margin:1rem 0;width:100%}}
td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
th{{background:#f2f2f2}} h1,h2{{font-weight:600}}
</style>
<h1>Replay review — {esc(meta.get('date', ''))} <small>(run {esc(meta.get('run', ''))})</small></h1>
<p>Day type: <b>{esc(dt.get('day_type', '?'))}</b> — {esc(dt.get('why', ''))}<br>
{meta.get('n_trades', 0):,} trades · {meta.get('n_bars', 0)} bars · bar N {esc(meta.get('bar_n', ''))}</p>
<h2>Recognitions ({len(p['confirmed'])} confirmed / {len(p['recognitions'])} total)</h2>
<table><tr><th>CT</th><th>setup</th><th>bias</th><th>anchor</th><th>state</th><th>stages</th><th>bar</th></tr>
{rec_rows or '<tr><td colspan=7>none</td></tr>'}</table>
<h2>Hindsight annotations ({len(p['annotations'])})</h2>
<table><tr><th>where</th><th>note</th></tr>
{ann_rows or '<tr><td colspan=2>none yet — scripts/replay_annotate.py</td></tr>'}</table>
<h2>Emission counts (latest run)</h2>
<table><tr><th>type</th><th>count</th></tr>{count_rows or '<tr><td colspan=2>none</td></tr>'}</table>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the replay review page [st-055]")
    ap.add_argument("--date", required=True, help="Replayed day YYYY-MM-DD")
    ap.add_argument("--out", help="Output HTML (default /tmp/desk-replay-review-<date>.html)")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date)
    spath = signals_path(day)
    if not spath.exists():
        print(f"no record for {day} at {spath} — run scripts/replay_day.py first",
              file=sys.stderr)
        return 1
    payload = review_payload(read_latest_run(spath), read_annotations(day))
    out = Path(args.out) if args.out else Path(f"/tmp/desk-replay-review-{day.isoformat()}.html")
    out.write_text(render_html(payload), encoding="utf-8")
    logger.info("wrote %s", out)
    if not args.no_open:
        open_in_browser(out)
    print(f"review ready: {out}  ({len(payload['confirmed'])} confirmed recognitions, "
          f"{len(payload['annotations'])} annotations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/scripts/test_replay_review.py -v`
Expected: 2 PASS

- [ ] **Step 5: End-to-end check on the real 07-02 record (written in Task 4)**

Run: `.venv/bin/python scripts/replay_review.py --date 2026-07-02 --no-open && head -c 400 /tmp/desk-replay-review-2026-07-02.html`
Expected: `review ready: ...` and the HTML head with the title line.

- [ ] **Step 6: Commit**

```bash
git add scripts/replay_review.py tests/scripts/test_replay_review.py
git commit -m "feat(scripts): hindsight review page — latest run + annotations [st-055]"
```

---

### Task 7: The drill workflow doc — `docs/drills/replay-week-workflow.md`

**Files:**
- Create: `docs/drills/replay-week-workflow.md`

- [ ] **Step 1: Create the doc with exactly this content**

```markdown
# FootPrint Replay Week — Drill Workflow (st-055)

Re-run a full week of DataBento RTH history through the production
classifier/recognizer stack, one day at a time, from the chair — same
FootPrint surface, same pipeline, every emission recorded for 20/20
hindsight review.

**Why this is faithful:** the computation path (reader → volume bars →
engine → stacks → recognizer) contains zero wall-clock reads — all time is
event time from the tape. The measured record is computed in one
deterministic batch pass; the drill surface renders the identical pipeline
with the identical anchor rule. Watching at speed 1× IS the live pacing
(bar duration ÷ speed, progressive intra-bar fill from real tape slices).

## The week

Target week **2026-07-13 → 2026-07-17** (most recent complete Mon–Fri
full-RTH week). The 07-06 → 07-10 week is equally replayable.

| Day | Date | ES trades on disk |
|-----|------------|---------|
| Mon | 2026-07-13 | 342,928 |
| Tue | 2026-07-14 | 278,031 |
| Wed | 2026-07-15 | 354,464 |
| Thu | 2026-07-16 | 339,526 |
| Fri | 2026-07-17 | 417,804 |

## One drill day, start to finish

1. **Launch** (COO runs it; Steve says "run Monday"):

       .venv/bin/python scripts/replay_day.py --date 2026-07-13

   This records the day (append-only, `data/measurement/replay/`), then
   opens the footprint drill in the browser. Optional: pin the day's levels
   with `--mancini-levels 6212,6230` — the SAME levels anchor both the
   record and the drill.

2. **Sit the session.** Set speed **1×**. Watch as-if-live. The optional
   coach channel works exactly as in normal drills
   (`scripts/drill_coach.sh start` before, `stop` after).

3. **Annotate in hindsight.** During or after the replay, Steve dictates;
   COO appends (never edits):

       .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 \
           --time 09:14 --text "flush into 6212 was the real one"

   Use `--bar N` instead of `--time` when the note is about a specific bar.

4. **Review.** Merge the record with the notes into the review page:

       .venv/bin/python scripts/replay_review.py --date 2026-07-13

   Day type, every recognition with its stages, emission counts, and the
   hindsight notes — this page (plus the raw JSONL) is the audit record
   for the recognizer review.

5. **Teardown.** Close the browser tab; `scripts/drill_coach.sh stop` if
   the bridge was up. The record and annotations persist under
   `data/measurement/replay/`; the HTML in `/tmp` is disposable.

## Invariants

- **No live-path contamination.** Corpus files are read-only inputs; the
  replay writes only under `data/measurement/replay/` and `/tmp`. No
  Schwab, no DataBento pulls.
- **Append-only record.** Re-running a day appends a new run block under a
  fresh `run_id`; nothing is rewritten. Review tools read the latest run;
  history stays.

## Troubleshooting

- `FileNotFoundError: no ES corpus file` — that date has no tape. Pick
  another day.
- No absorption rows in the record — the day has no MBP-1 file (07-23/24
  pending billing; the 07-06 week is trades-only). RunMeta says `mbp1: false`;
  everything else records normally. The target week 07-13..17 has full MBP-1.
- Empty recognitions — an unlabeled day anchors on range edges only;
  supply `--mancini-levels` to anchor the levels you traded.
- Out-of-order/duplicated tape (e.g. 2026-07-02) is safe: the reader
  dedups and canonically sorts before anything downstream sees it.
```

- [ ] **Step 2: Commit**

```bash
git add docs/drills/replay-week-workflow.md
git commit -m "docs(drills): replay-week drill workflow from the chair [st-055]"
```

---

### Task 8: Full suite, end-to-end day, close-out

- [ ] **Step 1: Full test run**

Run: `.venv/bin/python -m pytest`
Expected: all PASS (345 pre-existing + ~12 new), no skips introduced by this work.

- [ ] **Step 2: Full end-to-end on one target-week day**

Run: `.venv/bin/python scripts/replay_day.py --date 2026-07-13 --no-open`
Expected: `recorded: ...` then `drill ready: /tmp/desk-orderflow-drill-2026-07-13.html ...`. Verify the record: `wc -l data/measurement/replay/signals_2026-07-13.jsonl` (> 2 rows).

- [ ] **Step 3: Update the bead and push**

```bash
bd comment st-055 "Implementation complete per docs/superpowers/plans/2026-07-25-footprint-replay-drills.md — recorder, launcher, annotations, review page, workflow doc all tested. Week 2026-07-13..17 ready to drill."
git pull --rebase && git push
```

(Leave st-055 open until Steve has sat at least one replay day and the drill workflow is confirmed from the chair — the bead's AC includes the seat experience, not just the tooling.)

---

## Self-Review (performed 2026-07-25 while writing)

- **Spec coverage:** pacing model → header + Task 7 doc (decision: drill 1× + zero-wall-clock evidence); session setup/teardown → Tasks 4 & 7; capture format/storage → Task 3; hindsight annotations → Task 5; drill workflow from the seat → Task 7; constraints (no contamination, append-only) → invariants section + tests in Tasks 3 & 5.
- **Placeholder scan:** no TBDs, no "add error handling later", no "similar to Task N" — every code step carries its full code; every Run step names its command and expected outcome.
- **Type consistency:** `record_day` returns `meta | {"n_events", "day_type", "path"}` and Task 4 consumes exactly those keys; `full_stack_events(trades, *, bar_n, anchors, mancini_prices)` is called with the same signature in Tasks 2, 3; `annotations_path`/`signals_path` defined in Task 3, consumed in Tasks 5, 6; `beats` field name (code) vs "stages" (prose/UI) follows knowledge/stages-not-beats.
