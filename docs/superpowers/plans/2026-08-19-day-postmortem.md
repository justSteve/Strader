# Day Post-Mortem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily, unattended post-mortem of the trading day — what the recognizer called, what price did afterwards, the moves nothing called, Mancini's recap matched against the calls — as a ledger, a desk page, and flags for Strader, with a backfill over every tape day.

**Bead:** co-7kgte (**Post Mortem Process**). Spec: `docs/superpowers/specs/2026-08-19-day-postmortem-design.md`.

**Architecture:** One pure module `market/orderflow/postmortem.py` that takes `Segment`s (one feeder run: bars + events) and produces a day result dict, page markdown, and ledger rows — no CLI, no paths to the desk, no cron knowledge. A thin CLI `scripts/postmortem_day.py` loads live segments (via `market.orderflow.run_log.read_runs`) or replay segments (via the new `market/orderflow/replay_live.py`, extracted from `scripts/live_parity_check.py`), calls the module, writes the ledger, renders through COO's `desk-html.sh`, and registers once. A cron wrapper in the Strader pattern logs and alerts. Two `SCHEDULE.md` entries in COO generate the crontab.

**Tech Stack:** Python 3 stdlib + pyyaml (already in `.venv`), pytest, the existing orderflow stack (`run_log`, `replay`, `parity`, `anchors`, `bars`), `runbook.mancini.clean.html_to_text`, COO's `tmuxMOO/bin/desk-html.sh` and `desk-register.sh`.

**Run everything from `/root/projects/Strader` with `.venv/bin/python`.** Tests: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`. Commit after every task with `[co-7kgte]` in the message and add a row to `docs/a2a/inbox.md` on the final landing commit (Task 14).

---

## File structure

| Path | Responsibility |
|---|---|
| `market/orderflow/replay_live.py` (new) | `replay_events(day, *, bar_n, mancini)` — drive a day's tape exactly as the feeder drove it; moved out of `scripts/live_parity_check.py`, which re-exports it. |
| `market/orderflow/postmortem.py` (new) | Knobs, `Bar`, `Segment`, loaders, excursion, confirm lag, zigzag legs and tagging, recap extraction and matching, flags, `analyze_day`, ledger I/O, history, page markdown, backfill summary. |
| `config/postmortem.yaml` (new) | Steve-owned knobs. |
| `scripts/postmortem_day.py` (new) | CLI: `--day`, `--pass`, `--backfill`, `--workers`, `--no-publish`, `--dry-run`. Publishing and registration live here. |
| `scripts/cron/postmortem-wrapper.sh` (new) | Log, alert on failure, the morning smoke. |
| `scripts/live_parity_check.py` (modify) | Import `replay_events` from `replay_live`. |
| `scripts/acuity_run2.py` (modify) | Import `excursion_from_trades` from `postmortem` — the trade-level twin kept for its callers. |
| `tests/market/orderflow/test_postmortem.py`, `tests/market/orderflow/test_replay_live.py`, `tests/scripts/test_postmortem_day.py` (new), `tests/fixtures/postmortem/` (new) | Tests and the trimmed record fixture. |
| `/root/projects/COO/SCHEDULE.md` (modify) | Two cron entries. |

Data written at run time (not committed): `data/measurement/postmortem/{<day>.json, ledger.jsonl, legs.jsonl, backfill-days.json, recaps/<letter-date>.json, pages/postmortem-<day>.md, pages/postmortem-latest.md, pages/postmortem-backfill.md}` and `/var/moo/desk/desk-postmortem-{<day>,latest,backfill}.html`. Task 10 checks whether `data/measurement/` is already gitignored and adds `data/measurement/postmortem/` to `.gitignore` if not.

---

### Task 1: Extract `replay_events` into `market/orderflow/replay_live.py`

**Files:**
- Create: `market/orderflow/replay_live.py`
- Modify: `scripts/live_parity_check.py:77-109`
- Test: `tests/market/orderflow/test_replay_live.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/market/orderflow/test_replay_live.py
"""replay_events moved out of the parity checker so the post-mortem can drive
a day's tape the live way without importing a script. [co-7kgte]"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_module_exports_replay_events():
    from market.orderflow import replay_live
    assert callable(replay_live.replay_events)


def test_checker_reexports_the_same_function():
    path = REPO_ROOT / "scripts" / "live_parity_check.py"
    spec = importlib.util.spec_from_file_location("live_parity_check_rl", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    from market.orderflow.replay_live import replay_events
    assert mod.replay_events is replay_events
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_replay_live.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'market.orderflow.replay_live'`

- [ ] **Step 3: Create the module (body moved verbatim from the checker)**

```python
# market/orderflow/replay_live.py
"""Drive a day's tape exactly as the live feeder drove it. [st-x2mp, co-7kgte]

Closed bars only and ``LiveAnchors``, because those are the live rules (see
``market/orderflow/run_log.py``). Lived in ``scripts/live_parity_check.py``
until the day post-mortem needed the same drive for its backfill; a script is
not an importable home, so the function moved here and the checker imports it.
"""
from __future__ import annotations

from datetime import date as _date

from market.orderflow.anchors import LiveAnchors
from market.orderflow.bars import build_bars
from market.orderflow.parity import StackDriver, live_drive
from market.orderflow.replay import read_corpus_day
from market.orderflow.run_log import bar_record


def replay_events(day: _date, *, bar_n: int, mancini: list[float]) -> tuple[list[dict], list[dict]]:
    """Returns ``(bar_records, emissions)`` in the shape the run log holds them."""
    trades = read_corpus_day(day)
    live_anchors = LiveAnchors(mancini)
    driver = StackDriver(anchors=live_anchors.anchors, mancini_prices=mancini)
    pending = list(trades)
    cursor = {"i": 0}

    def _closed_bars():
        # Bars close on known trade boundaries, so walk the trade list until
        # each bar's volume is covered — the same straddle convention the
        # feeder's take_bar_trades() reclaims a slice by.
        for bar in build_bars(iter(trades), n=bar_n):
            vol = 0
            start = cursor["i"]
            while cursor["i"] < len(pending) and vol < bar.volume:
                vol += pending[cursor["i"]].size
                cursor["i"] += 1
            yield bar, pending[start:cursor["i"]]

    bars: list[dict] = []
    events: list[dict] = []
    for bar_i, bar, _trades, evs in live_drive(_closed_bars(), driver, live_anchors):
        bars.append(bar_record(bar_i, bar))
        events.extend({"k": "ev"} | e for e in evs)
    events.extend({"k": "ev"} | e for e in driver.finish(pending[cursor["i"]:]))
    return bars, events
```

- [ ] **Step 4: Replace the checker's copy with an import**

In `scripts/live_parity_check.py`, delete the whole `def replay_events(...)` function (lines 77–109) and add to the import block (after the `run_log` import):

```python
from market.orderflow.replay_live import replay_events                   # noqa: E402,F401 — re-exported for callers
```

Then `grep -n "LiveAnchors\|build_bars\|StackDriver\|live_drive\|read_corpus_day" scripts/live_parity_check.py` and remove any import whose only hit is the import line itself (`has_es_day` stays — `main` uses it).

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_replay_live.py tests/market/orderflow/test_run_log.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add market/orderflow/replay_live.py scripts/live_parity_check.py tests/market/orderflow/test_replay_live.py
git commit -m "replay_live: replay_events moved out of the parity checker so the post-mortem backfill can import it [co-7kgte]"
```

---

### Task 2: Knobs and config file

**Files:**
- Create: `market/orderflow/postmortem.py`
- Create: `config/postmortem.yaml`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/market/orderflow/test_postmortem.py
"""Day post-mortem: measuring, legs, recap, flags, page. [co-7kgte]

Every number on the page is a rule; these tests pin the rules on hand-built
bars so a change to any rule is a visible diff here first.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market.orderflow import postmortem as pm

CT = ZoneInfo("America/Chicago")
T0 = datetime(2026, 8, 18, 8, 30, tzinfo=CT)
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "postmortem" / "2026-08-18-trimmed.jsonl"


# ----------------------------------------------------------------- helpers

def _bar(i: int, o: float, h: float, l: float, c: float, *, d: int = 0,
         minute: int | None = None) -> pm.Bar:
    """One bar per minute from T0 unless ``minute`` is given."""
    m = i if minute is None else minute
    t0 = T0 + timedelta(minutes=m)
    return pm.Bar(i=i, t0=t0, t1=t0 + timedelta(seconds=55), o=o, h=h, l=l, c=c, v=2000, d=d)


def _ev(bar_i: int, bars: list[pm.Bar], **fields) -> dict:
    base = {"k": "ev", "type": "SetupRecognition", "bar_i": bar_i,
            "timestamp": bars[bar_i].t1.isoformat(), "confidence": 0.8,
            "reason": "x", "source": "orderflow.recognizer"}
    return base | fields


def _segment(bars, events, *, mancini=(), run_no=1, complete=True) -> pm.Segment:
    return pm.Segment(run_no=run_no, bars=list(bars), events=list(events),
                      meta={"bar_n": 2000, "mancini": list(mancini),
                            "started": T0.isoformat()},
                      complete=complete)


def _knobs_dict(k: pm.Knobs) -> dict:
    d = asdict(k)
    d["windows_min"] = list(d["windows_min"])
    return d


# ------------------------------------------------------------------- knobs

def test_default_knobs_match_spec():
    k = pm.Knobs()
    assert (k.x_pts, k.y_min, k.z_pts, k.w_min) == (6.0, 15, 3.0, 10)
    assert k.windows_min == (5, 15, 30)
    assert k.target_pts == 5.0
    assert (k.dense_anchor_fires, k.late_confirm_bars, k.late_confirm_pts,
            k.breakout_pts, k.grid_density) == (5, 2, 3.0, 10.0, 8.0)


def test_load_knobs_reads_yaml_and_falls_back(tmp_path):
    p = tmp_path / "postmortem.yaml"
    p.write_text("x_pts: 8\ny_min: 20\n")
    k = pm.load_knobs(p)
    assert (k.x_pts, k.y_min) == (8.0, 20)
    assert k.z_pts == 3.0                       # untouched keys keep defaults
    assert pm.load_knobs(tmp_path / "absent.yaml") == pm.Knobs()


def test_load_knobs_rejects_unknown_key(tmp_path):
    p = tmp_path / "postmortem.yaml"
    p.write_text("x_pts: 8\nbogus: 1\n")
    with pytest.raises(ValueError, match="bogus"):
        pm.load_knobs(p)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: FAIL — `ImportError: cannot import name 'postmortem'`

- [ ] **Step 3: Write the module skeleton with Knobs**

```python
# market/orderflow/postmortem.py
"""Day post-mortem — what the recognizer called, what followed, what it missed. [co-7kgte]

Spec: docs/superpowers/specs/2026-08-19-day-postmortem-design.md.

Pure module. Takes Segments (one feeder run each: bars + events), returns a
day result dict, ledger rows and page markdown. Knows nothing about the desk,
cron, or which day is "today" — scripts/postmortem_day.py does. Every number
here is a rule with its threshold in ``Knobs``; nothing judges.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from dataclasses import asdict, dataclass, fields, replace
from datetime import date as _date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "postmortem.yaml"
LEDGER_ROOT = REPO_ROOT / "data" / "measurement" / "postmortem"


@dataclass(frozen=True)
class Knobs:
    """Every threshold on the page. Steve owns the numbers (config/postmortem.yaml)."""
    x_pts: float = 6.0            # leg size
    y_min: int = 15               # leg must reach x_pts inside this many minutes
    z_pts: float = 3.0            # "near a level" distance
    w_min: int = 10               # look-back for calls before a leg
    windows_min: tuple = (5, 15, 30)
    target_pts: float = 5.0       # first-touch grade
    dense_anchor_fires: int = 5
    late_confirm_bars: int = 2
    late_confirm_pts: float = 3.0
    breakout_pts: float = 10.0
    grid_density: float = 8.0     # confirms per 10 pts of session range
    history_days: int = 20


def knobs_to_dict(k: Knobs) -> dict:
    d = asdict(k)
    d["windows_min"] = list(d["windows_min"])
    return d


def knobs_from_dict(d: dict) -> Knobs:
    d = dict(d)
    if "windows_min" in d:
        d["windows_min"] = tuple(int(w) for w in d["windows_min"])
    return Knobs(**d)


def load_knobs(path: Path = CONFIG_PATH) -> Knobs:
    """Knobs from yaml over the defaults. Unknown keys are an error — a typo
    that silently kept the default is the failure this guards."""
    if not path.exists():
        return Knobs()
    import yaml
    doc = yaml.safe_load(path.read_text()) or {}
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: expected a mapping")
    known = {f.name for f in fields(Knobs)}
    bad = sorted(set(doc) - known)
    if bad:
        raise ValueError(f"{path}: unknown knob(s) {bad}; known: {sorted(known)}")
    if "windows_min" in doc:
        doc["windows_min"] = tuple(int(w) for w in doc["windows_min"])
    return replace(Knobs(), **doc)
```

- [ ] **Step 4: Write the config file**

```yaml
# config/postmortem.yaml — Day Post-Mortem thresholds. [co-7kgte]
#
# Steve owns every number here; edit and commit. Read at the start of each
# pass (15:30 same-day, 08:27 next-morning) — a mid-afternoon edit changes
# that day's 15:30 page. Every key is a field of Knobs in
# market/orderflow/postmortem.py; an unknown key stops the run rather than
# silently keeping a default. Units: ES points and minutes.

x_pts: 6            # a leg counts when price moves this far against the prior extreme
y_min: 15           # ...and reached it inside this many minutes of the leg's origin
z_pts: 3            # a leg is "near a level" when its origin is within this of an anchor
w_min: 10           # calls in the leg's direction are looked for this far before the origin
windows_min: [5, 15, 30]   # for/against measured at each of these minutes after a call
target_pts: 5       # first-touch grade: win/loss at ±this from the call's close
dense_anchor_fires: 5      # flag: one anchor confirmed at least this many times in a day
late_confirm_bars: 2       # flag: confirm this many bars after the reclaim, or...
late_confirm_pts: 3        # ...this many points past the anchor at the confirm close
breakout_pts: 10           # flag: a leg this big through a level with only "invalidated" said
grid_density: 8            # flag: confirmed setups per 10 points of session range
history_days: 20           # the "last N days" section
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add market/orderflow/postmortem.py config/postmortem.yaml tests/market/orderflow/test_postmortem.py
git commit -m "postmortem: Knobs and config/postmortem.yaml — every threshold on the page in one Steve-owned file [co-7kgte]"
```

---

### Task 3: `Bar`, `Segment`, and the loaders

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Create: `tests/fixtures/postmortem/2026-08-18-trimmed.jsonl`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Cut the fixture from the real 2026-08-18 record**

Two runs: the file's first run header with the session run's first 3 bars under it (the point is two headers and run splitting), then the session run's header with its bars 380–420 (feeder numbering; 13:01–13:35 CT, the bar-339 neighbourhood — page bar 338 is feeder bar 395) and every event whose `bar_i` is in that range, and `end` rows.

```bash
mkdir -p tests/fixtures/postmortem
.venv/bin/python - <<'EOF'
import json
from pathlib import Path
src = Path("data/derived/live-parity/2026-08-18.jsonl")
out = Path("tests/fixtures/postmortem/2026-08-18-trimmed.jsonl")
runs = []
for line in src.read_text().splitlines():
    rec = json.loads(line)
    if rec["k"] == "run":
        runs.append([rec])
    else:
        runs[-1].append(rec)
main = next(r for r in reversed(runs) if any(x["k"] == "bar" for x in r))
lines = [runs[0][0]]
lines += [x for x in main if x["k"] == "bar" and x["i"] < 3]
lines.append({"k": "end", "bars": 3, "events": 0})
lines.append(main[0])
keep = [x for x in main if (x["k"] == "bar" and 380 <= x["i"] <= 420)
        or (x["k"] == "ev" and x.get("bar_i") is not None and 380 <= x["bar_i"] <= 420)]
lines += keep
lines.append({"k": "end", "bars": 41, "events": sum(1 for x in keep if x["k"] == "ev")})
out.write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in lines) + "\n")
conf = [x for x in keep if x["k"] == "ev" and x["type"] == "SetupRecognition" and x["state"] == "confirmed"]
print(len(lines), "lines;", sum(1 for x in keep if x["k"]=="ev"), "events;", [(c["bar_i"], c["anchor_price"]) for c in conf])
EOF
```

Expected: roughly 60–120 lines, and the printed confirmed list includes `(395, 7720.0)`. If the confirm sits at a different bar number, use the printed number in the test below instead of 395 (the record is the truth, the page's "338" was page numbering).

- [ ] **Step 2: Write the failing tests**

Append to `tests/market/orderflow/test_postmortem.py`:

```python
# ---------------------------------------------------------------- loaders

def test_bar_from_record_parses_times_and_prices():
    rec = {"k": "bar", "i": 7, "t0": "2026-08-18T08:30:15-05:00",
           "t1": "2026-08-18T08:31:05-05:00", "o": 7720.0, "h": 7721.5,
           "l": 7719.75, "c": 7721.0, "v": 2000, "d": 120, "nv": 0}
    b = pm.Bar.from_record(rec)
    assert b.i == 7 and b.h == 7721.5 and b.d == 120
    assert b.t0.tzinfo is not None and b.t0.hour == 8 and b.t1.minute == 31


def test_load_live_segments_splits_runs_and_keeps_feeder_bar_numbers():
    segs = pm.load_live_segments(FIXTURE)
    assert [s.run_no for s in segs] == [1, 2]
    assert len(segs[0].bars) == 3 and segs[0].bars[0].i == 0
    assert segs[1].bars[0].i == 380 and segs[1].bars[-1].i == 420
    assert all(e["bar_i"] is None or 380 <= e["bar_i"] <= 420 for e in segs[1].events)
    assert 7720.0 in segs[1].mancini
    assert segs[1].complete is True
    confirmed = [e for e in segs[1].events
                 if e["type"] == "SetupRecognition" and e["state"] == "confirmed"]
    assert any(e["anchor_price"] == 7720.0 and e["bar_i"] == 395 for e in confirmed)


def test_load_live_segments_skips_runs_without_bar_n(tmp_path, caplog):
    p = tmp_path / "x.jsonl"
    p.write_text('{"k":"run","day":"2026-08-18","mancini":[]}\n'
                 '{"k":"bar","i":0,"t0":"2026-08-18T08:30:00-05:00","t1":"2026-08-18T08:31:00-05:00",'
                 '"o":1,"h":2,"l":0,"c":1,"v":2000,"d":0,"nv":0}\n')
    with caplog.at_level("WARNING"):
        segs = pm.load_live_segments(p)
    assert segs == []
    assert "bar_n" in caplog.text


def test_segment_pos_maps_bar_number_to_index():
    bars = [_bar(i + 10, 10, 11, 9, 10) for i in range(3)]     # numbered 10, 11, 12
    seg = _segment(bars, [])
    assert seg.pos(11) == 1
    assert seg.pos(99) is None and seg.pos(None) is None
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k "bar_from or load_live or segment_pos"`
Expected: FAIL — `AttributeError: module ... has no attribute 'Bar'`

- [ ] **Step 4: Implement Bar, Segment, loaders**

Append to `market/orderflow/postmortem.py`:

```python
# ------------------------------------------------------------------ inputs

@dataclass(frozen=True)
class Bar:
    """One volume bar as the run log records it (run_log.bar_record)."""
    i: int
    t0: datetime
    t1: datetime
    o: float
    h: float
    l: float
    c: float
    v: int
    d: int

    @classmethod
    def from_record(cls, rec: dict) -> "Bar":
        return cls(i=int(rec["i"]),
                   t0=datetime.fromisoformat(rec["t0"]),
                   t1=datetime.fromisoformat(rec["t1"]),
                   o=float(rec["o"]), h=float(rec["h"]), l=float(rec["l"]),
                   c=float(rec["c"]), v=int(rec["v"]), d=int(rec["d"]))


@dataclass
class Segment:
    """One feeder run: its bars, its emissions, its header. Bars keep the
    feeder's own numbering (``Bar.i``); ``pos`` maps a bar number to a list
    index, because a trimmed or restarted run need not start at zero."""
    run_no: int
    bars: list
    events: list
    meta: dict
    complete: bool = True

    def __post_init__(self) -> None:
        self._pos = {b.i: k for k, b in enumerate(self.bars)}

    def pos(self, bar_i) -> int | None:
        if bar_i is None:
            return None
        return self._pos.get(int(bar_i))

    @property
    def mancini(self) -> list[float]:
        return [float(x) for x in (self.meta.get("mancini") or [])]

    @property
    def bar_n(self) -> int:
        return int(self.meta.get("bar_n") or 0)

    @property
    def started(self) -> str:
        return str(self.meta.get("started", "?"))

    @property
    def span(self) -> tuple[datetime, datetime] | None:
        if not self.bars:
            return None
        return self.bars[0].t0, self.bars[-1].t1


def load_live_segments(path: Path) -> list[Segment]:
    """The feeder's record of a day → Segments, one per run with bars.

    Runs without ``bar_n`` (an older feeder) are skipped with a warning, never
    guessed at; runs with no bars (a header and an immediate end) are dropped
    silently — they carry nothing to measure. Run numbers count every header
    in the file, skipped or not, so the page's run number matches the file.
    """
    from market.orderflow.run_log import read_runs
    out: list[Segment] = []
    for n, run in enumerate(read_runs(path), start=1):
        if not run.bar_n:
            logger.warning("%s run %d (started %s): header carries no bar_n — skipped",
                           path.name, n, run.started)
            continue
        if not run.bars:
            continue
        out.append(Segment(run_no=n, bars=[Bar.from_record(b) for b in run.bars],
                           events=list(run.events), meta=run.meta, complete=run.complete))
    return out


def segments_from_replay(day: _date, *, bar_n: int, mancini: list[float]) -> list[Segment]:
    """One Segment from a full replay of the day's tape (backfill path)."""
    from market.orderflow.replay_live import replay_events
    bars, events = replay_events(day, bar_n=bar_n, mancini=mancini)
    if not bars:
        return []
    meta = {"bar_n": bar_n, "mancini": list(mancini), "started": bars[0]["t0"],
            "replay": True}
    return [Segment(run_no=1, bars=[Bar.from_record(b) for b in bars],
                    events=events, meta=meta, complete=True)]
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS (7 so far).

- [ ] **Step 6: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py tests/fixtures/postmortem/2026-08-18-trimmed.jsonl
git commit -m "postmortem: Bar, Segment, live and replay loaders; trimmed 2026-08-18 record as fixture (two runs, bars 380-420) [co-7kgte]"
```

---

### Task 4: Excursion from bars

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# -------------------------------------------------------------- excursion

def test_excursion_for_and_against_from_bars():
    # entry 100 at bar 0 close; next bars: up to 103, down to 98, up to 106
    bars = [_bar(0, 100, 100, 100, 100),
            _bar(1, 100, 103, 99.5, 102),
            _bar(2, 102, 102, 98, 99),
            _bar(3, 99, 106, 99, 105)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[0].t1 + timedelta(minutes=30), target=5.0)
    assert r == pm.Excursion(mfe=6.0, mae=2.0, verdict="win", truncated=True)
    r = pm.excursion(bars, start=0, entry=100.0, sign=-1,
                     until=bars[0].t1 + timedelta(minutes=30), target=5.0)
    assert (r.mfe, r.mae, r.verdict) == (2.0, 6.0, "loss")


def test_excursion_window_stops_at_until():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 101, 99, 100),
            _bar(2, 100, 120, 100, 119)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[1].t1, target=5.0)
    assert (r.mfe, r.mae, r.verdict, r.truncated) == (1.0, 1.0, "neither", False)


def test_excursion_both_in_one_bar_is_named_not_guessed():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 106, 94, 100)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[1].t1, target=5.0)
    assert r.verdict == "both-in-one-bar"
    assert (r.mfe, r.mae) == (6.0, 6.0)


def test_excursion_truncated_when_record_ends_before_until():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 101, 99, 100)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[1].t1 + timedelta(minutes=30), target=5.0)
    assert r.truncated is True and r.verdict == "neither"
```

Note the first test: four one-minute bars cannot fill a 30-minute window, so `truncated=True` there is correct, and the verdict still grades on what was seen.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k excursion`
Expected: FAIL — `AttributeError: ... 'excursion'`

- [ ] **Step 3: Implement**

```python
# --------------------------------------------------------------- measuring

@dataclass(frozen=True)
class Excursion:
    mfe: float          # furthest the call's way, points
    mae: float          # furthest against, points
    verdict: str        # win | loss | neither | both-in-one-bar
    truncated: bool     # the record ended before ``until``


def excursion(bars: list, *, start: int, entry: float, sign: int,
              until: datetime, target: float) -> Excursion:
    """For/against from ``entry`` over bars after index ``start`` until ``until``.

    The bar-level twin of acuity_run2's trade-level function: highs and lows
    stand in for prints. First touch at ±target is graded bar by bar; a bar
    whose range covers both sides before either was touched alone is reported
    as such, not resolved by a coin.
    """
    mfe = mae = 0.0
    verdict = "neither"
    last_t1 = bars[start].t1
    for b in bars[start + 1:]:
        if b.t0 > until:
            break
        last_t1 = b.t1
        up = sign * (b.h - entry)
        dn = sign * (b.l - entry)
        hi, lo = max(up, dn), min(up, dn)
        mfe = max(mfe, hi)
        mae = max(mae, -lo)
        if verdict == "neither":
            hit_for, hit_against = hi >= target, -lo >= target
            if hit_for and hit_against:
                verdict = "both-in-one-bar"
            elif hit_for:
                verdict = "win"
            elif hit_against:
                verdict = "loss"
    return Excursion(mfe=round(mfe, 2), mae=round(mae, 2), verdict=verdict,
                     truncated=last_t1 < until)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py
git commit -m "postmortem: excursion from bars — for/against, ±target first touch, both-in-one-bar named, truncated window flagged [co-7kgte]"
```

---

### Task 5: Measuring the calls (rows, nth-on-level, confirm lag, back-to-level)

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# ------------------------------------------------------------------ calls

def _flush_reclaim_confirm():
    """Anchor 7720. Bars: above, flush below (bar 2), stay below, first close
    back above at bar 5 (the reclaim), confirm at bar 7 (lag 2) with close
    7723.75 (+3.75 from the anchor). Then a drift back under the level at
    bar 12 (back-to-level after 5 minutes)."""
    closes = [7721, 7720.5, 7718, 7716, 7717, 7721.5, 7721.5, 7723.75,
              7724, 7723, 7722, 7721, 7719.5, 7719, 7720.5, 7722]
    bars = [_bar(i, c, c + 0.75, c - 0.75, c) for i, c in enumerate(closes)]
    events = [
        _ev(2, bars, setup="failed_breakdown", bias="bullish", anchor_price=7720.0,
            anchor_kind="support", state="forming", beats=["flush"], fire_index=1,
            confidence=0.35, mancini_confluence=True),
        _ev(7, bars, setup="failed_breakdown", bias="bullish", anchor_price=7720.0,
            anchor_kind="support", state="confirmed", beats=["flush", "flip", "stall", "confirm"],
            fire_index=1, confidence=0.8, mancini_confluence=True),
        _ev(9, bars, type="SweepPrint", direction="buy", start_price=7723.0,
            end_price=7724.5, ticks_swept=6, total_size=300, confidence=1.0),
    ]
    return bars, events


def test_measure_calls_rows_and_confirm_lag():
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    rows = pm.measure_calls(seg, pm.Knobs())
    kinds = [(r["type"], r.get("state")) for r in rows]
    assert ("SetupRecognition", "confirmed") in kinds and ("SweepPrint", None) in kinds
    assert ("SetupRecognition", "forming") not in kinds       # counted elsewhere, not measured
    c = next(r for r in rows if r.get("state") == "confirmed")
    assert c["bar_i"] == 7 and c["entry"] == 7723.75 and c["direction"] == "bullish"
    assert c["fire_index"] == 1 and c["anchor"] == 7720.0
    assert c["confirm_lag_bars"] == 2 and c["confirm_lag_pts"] == 3.75
    assert c["back_to_level_min"] == 5            # bar 12 closes under 7720
    assert c["mfe5"] >= 0 and "verdict30" in c and "truncated30" in c
    s = next(r for r in rows if r["type"] == "SweepPrint")
    assert s["direction"] == "bullish" and s["entry"] == 7723.0 and s["anchor"] is None


def test_measure_calls_direction_mapping_and_invalidated_sign():
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(4)]
    events = [
        _ev(0, bars, type="DeltaDivergence", kind="bearish", price_extreme=100.0,
            prior_extreme=99.0, cvd_at_extreme=1, cvd_at_prior=2),
        _ev(1, bars, type="ImbalanceStack", direction="sell", prices=[100.0], ratios=[3.0]),
        _ev(2, bars, setup="level_reclaim", bias="bullish", anchor_price=99.0,
            anchor_kind="support", state="invalidated", beats=[], fire_index=2, confidence=0.0),
    ]
    rows = pm.measure_calls(_segment(bars, events), pm.Knobs())
    assert [r["direction"] for r in rows] == ["bearish", "bearish", "bullish"]
    assert rows[2]["state"] == "invalidated"


def test_measure_calls_skips_events_without_a_known_bar():
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(2)]
    ev = _ev(0, bars, type="Level", price=100.0, level_type="support")
    ev["bar_i"] = None
    rows = pm.measure_calls(_segment(bars, [ev]), pm.Knobs())
    assert rows == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k measure_calls`
Expected: FAIL — `AttributeError: ... 'measure_calls'`

- [ ] **Step 3: Implement**

```python
MEASURED_TYPES = ("SetupRecognition", "DeltaDivergence", "SweepPrint", "ImbalanceStack")


def direction_of(ev: dict) -> str | None:
    """bullish | bearish | None. One place for every emitter's field name."""
    t = ev.get("type")
    if t == "SetupRecognition":
        return ev.get("bias")
    if t == "DeltaDivergence":
        return ev.get("kind")
    if t in ("SweepPrint", "ImbalanceStack"):
        return {"buy": "bullish", "sell": "bearish"}.get(ev.get("direction"))
    return None


def _sign(direction: str) -> int:
    return 1 if direction == "bullish" else -1


def _right_side(price: float, anchor: float, direction: str) -> bool:
    """Is ``price`` on the setup's side of the anchor?"""
    return price > anchor if direction == "bullish" else price < anchor


def confirm_lag(seg: Segment, ev: dict) -> tuple[int | None, float | None]:
    """(bars from the reclaim to the confirm, points past the anchor at the
    confirm close). The reclaim is the first close back on the setup's side
    of the anchor after the flush bar; the flush bar is the earliest
    ``forming`` beat for the same (anchor, setup, fire_index). Without one the
    lag is None and the points still report."""
    k = seg.pos(ev.get("bar_i"))
    if k is None:
        return None, None
    anchor = float(ev["anchor_price"])
    direction = ev.get("bias") or "bullish"
    pts = round(_sign(direction) * (seg.bars[k].c - anchor), 2)
    key = (ev.get("anchor_price"), ev.get("setup"), ev.get("fire_index"))
    forming_pos = [seg.pos(e.get("bar_i")) for e in seg.events
                   if e.get("type") == "SetupRecognition" and e.get("state") == "forming"
                   and (e.get("anchor_price"), e.get("setup"), e.get("fire_index")) == key]
    forming_pos = [p for p in forming_pos if p is not None and p <= k]
    if not forming_pos:
        return None, pts
    for j in range(min(forming_pos) + 1, k + 1):
        if _right_side(seg.bars[j].c, anchor, direction):
            return k - j, pts
    return 0, pts


def back_to_level(seg: Segment, k: int, anchor: float, direction: str,
                  until: datetime) -> int | None:
    """Minutes until the first close back on the wrong side of ``anchor``
    after bar index ``k``, inside ``until``; None if it never happened."""
    for b in seg.bars[k + 1:]:
        if b.t0 > until:
            return None
        if not _right_side(b.c, anchor, direction) and b.c != anchor:
            return int(round((b.t1 - seg.bars[k].t1).total_seconds() / 60))
    return None


def measure_calls(seg: Segment, knobs: Knobs) -> list[dict]:
    """One row per measured emission (spec §3a). ``forming`` beats and
    ``Level`` rows are not measured; events without a known bar are skipped
    (end-of-stream flush signals, profile levels)."""
    rows: list[dict] = []
    for ev in seg.events:
        if ev.get("type") not in MEASURED_TYPES:
            continue
        if ev.get("type") == "SetupRecognition" and ev.get("state") == "forming":
            continue
        k = seg.pos(ev.get("bar_i"))
        if k is None:
            continue
        direction = direction_of(ev)
        if direction not in ("bullish", "bearish"):
            continue
        bar = seg.bars[k]
        entry = float(ev.get("start_price", bar.c)) if ev["type"] == "SweepPrint" else bar.c
        row = {
            "run": seg.run_no, "bar_i": bar.i, "ct": bar.t1.strftime("%H:%M"),
            "t1": bar.t1.isoformat(), "type": ev["type"],
            "setup": ev.get("setup"), "state": ev.get("state"),
            "direction": direction, "entry": entry,
            "confidence": ev.get("confidence"), "reason": ev.get("reason"),
            "anchor": (float(ev["anchor_price"]) if ev.get("anchor_price") is not None else None),
            "fire_index": ev.get("fire_index"),
            "confirm_lag_bars": None, "confirm_lag_pts": None,
            "back_to_level_min": None,
        }
        for w in knobs.windows_min:
            ex = excursion(seg.bars, start=k, entry=entry, sign=_sign(direction),
                           until=bar.t1 + timedelta(minutes=w), target=knobs.target_pts)
            row[f"mfe{w}"] = ex.mfe
            row[f"mae{w}"] = ex.mae
            row[f"verdict{w}"] = ex.verdict
            row[f"truncated{w}"] = ex.truncated
        if ev["type"] == "SetupRecognition" and row["anchor"] is not None:
            if ev.get("state") == "confirmed":
                row["confirm_lag_bars"], row["confirm_lag_pts"] = confirm_lag(seg, ev)
            row["back_to_level_min"] = back_to_level(
                seg, k, row["anchor"], direction,
                bar.t1 + timedelta(minutes=max(knobs.windows_min)))
        rows.append(row)
    return rows
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS. If `back_to_level_min` is off, check the fixture closes: bar 12 close 7719.5 is the first close under 7720 after bar 7; minutes = bar12.t1 − bar7.t1 = 5.

- [ ] **Step 5: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py
git commit -m "postmortem: measure_calls — one row per directional emission with for/against at each window, ±5 touch, nth-on-level, confirm lag, back-to-level [co-7kgte]"
```

---

### Task 6: Zigzag legs and tagging (the "moves nothing said" half)

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# ------------------------------------------------------------------- legs

def _path(closes, *, spread=0.5):
    return [_bar(i, c, c + spread, c - spread, c) for i, c in enumerate(closes)]


def test_zigzag_legs_threshold_and_window():
    # up 8 in 5 minutes (kept), down 5 (dropped: < X), up 9 over 45 bars (dropped: > Y)
    closes = [100, 101, 103, 104, 106, 108, 108,
              107, 106, 105, 104, 103] + [103 + 0.2 * n for n in range(1, 46)]
    bars = _path(closes, spread=0.0)
    knobs = pm.Knobs(x_pts=6.0, y_min=15)
    legs = pm.zigzag_legs(bars, knobs.x_pts)
    kept = pm.keep_legs(legs, knobs)
    assert [round(l.pts, 1) for l in kept] == [8.0]
    a = kept[0]
    assert a.direction == "bullish" and a.origin_i == 0 and a.pts == 8.0
    assert a.end_i == 5 and a.minutes == 5 and a.reached_x_min <= 15


def test_zigzag_uses_highs_and_lows_not_closes():
    # closes flat, but bar 2 spikes 7 points high then back: one up leg, one down leg
    bars = [_bar(0, 100, 100.5, 99.5, 100), _bar(1, 100, 100.5, 99.5, 100),
            _bar(2, 100, 107, 99.5, 100), _bar(3, 100, 100.5, 99.5, 100),
            _bar(4, 100, 100.5, 99.5, 100)]
    legs = pm.zigzag_legs(bars, 6.0)
    assert [l.direction for l in legs][:2] == ["bullish", "bearish"]
    assert legs[0].pts == 7.5          # 99.5 low → 107 high


def test_tag_legs_called_hinted_silent_and_near_level():
    bars, events = _flush_reclaim_confirm()     # confirm at bar 7, sweep at bar 9
    # then a 10-point up leg from bar 16 (7723) → bar 20 (7731), inside W of the sweep
    extra = [_bar(16 + n, 7723 + 2 * n, 7723 + 2 * n + 0.5, 7723 + 2 * n - 0.5, 7723 + 2 * n)
             for n in range(5)]
    seg = _segment(bars + extra, events, mancini=[7720.0, 7734.0])
    knobs = pm.Knobs(x_pts=6.0, y_min=15, z_pts=3.0, w_min=10)
    legs = pm.keep_legs(pm.zigzag_legs(seg.bars, knobs.x_pts), knobs)
    tagged = pm.tag_legs(legs, seg, anchors=seg.mancini, knobs=knobs)
    up = [t for t in tagged if t["direction"] == "bullish"]
    assert up, "expected a kept bullish leg"
    assert up[-1]["tag"] in ("called", "hinted")      # a confirm or sweep preceded it
    assert up[-1]["nearest_level"] in (7720.0, 7734.0)
    assert "near_level" in up[-1] and "said_before" in up[-1]


def test_tag_legs_silent_when_nothing_in_window():
    bars = _path([100, 100, 100, 100, 101, 103, 105, 107, 108])
    seg = _segment(bars, [], mancini=[101.0])
    knobs = pm.Knobs(x_pts=6.0, y_min=15, z_pts=3.0, w_min=10)
    tagged = pm.tag_legs(pm.keep_legs(pm.zigzag_legs(bars, 6.0), knobs), seg,
                         anchors=[101.0], knobs=knobs)
    assert len(tagged) == 1 and tagged[0]["tag"] == "silent" and tagged[0]["near_level"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k "zigzag or tag_legs"`
Expected: FAIL — `AttributeError: ... 'zigzag_legs'`

- [ ] **Step 3: Implement**

```python
# ------------------------------------------------------------------- legs

@dataclass
class Leg:
    direction: str        # bullish | bearish
    origin_i: int         # list index into seg.bars (NOT feeder bar number)
    end_i: int
    origin_px: float
    end_px: float
    minutes: int = 0
    reached_x_min: int | None = None

    @property
    def pts(self) -> float:
        return round(abs(self.end_px - self.origin_px), 2)


def zigzag_legs(bars: list, x_pts: float) -> list[Leg]:
    """Legs between alternating extremes, using highs and lows. A new leg is
    opened when price has moved ``x_pts`` against the running extreme of the
    current one; the first touch of an extreme is the leg's end (a later
    equal high does not move it). The last, unfinished leg is included — it
    is what the day ended doing."""
    if not bars:
        return []
    legs: list[Leg] = []
    lo_i = hi_i = 0
    lo, hi = bars[0].l, bars[0].h
    direction: str | None = None
    origin_i, origin_px, ext_i, ext_px = 0, bars[0].c, 0, bars[0].c
    for k, b in enumerate(bars):
        if direction is None:
            if b.h > hi:
                hi, hi_i = b.h, k
            if b.l < lo:
                lo, lo_i = b.l, k
            if hi - lo >= x_pts:
                if hi_i >= lo_i:        # rose from the low: bullish leg from lo
                    direction, origin_i, origin_px, ext_i, ext_px = "bullish", lo_i, lo, hi_i, hi
                else:
                    direction, origin_i, origin_px, ext_i, ext_px = "bearish", hi_i, hi, lo_i, lo
            continue
        if direction == "bullish":
            if b.h > ext_px:
                ext_i, ext_px = k, b.h
            elif ext_px - b.l >= x_pts:
                legs.append(Leg("bullish", origin_i, ext_i, origin_px, ext_px))
                direction, origin_i, origin_px, ext_i, ext_px = "bearish", ext_i, ext_px, k, b.l
        else:
            if b.l < ext_px:
                ext_i, ext_px = k, b.l
            elif b.h - ext_px >= x_pts:
                legs.append(Leg("bearish", origin_i, ext_i, origin_px, ext_px))
                direction, origin_i, origin_px, ext_i, ext_px = "bullish", ext_i, ext_px, k, b.h
    if direction is not None:
        legs.append(Leg(direction, origin_i, ext_i, origin_px, ext_px))
    for leg in legs:
        o, e = bars[leg.origin_i], bars[leg.end_i]
        leg.minutes = int(round((e.t1 - o.t1).total_seconds() / 60))
        sign = 1 if leg.direction == "bullish" else -1
        for b in bars[leg.origin_i:leg.end_i + 1]:
            far = sign * ((b.h if sign > 0 else b.l) - leg.origin_px)
            if far >= x_pts:
                leg.reached_x_min = int(round((b.t1 - o.t1).total_seconds() / 60))
                break
    return legs


def keep_legs(legs: list[Leg], knobs: Knobs) -> list[Leg]:
    """Spec §3b step 2: at least X points, and X reached inside Y minutes."""
    return [l for l in legs
            if l.pts >= knobs.x_pts and l.reached_x_min is not None
            and l.reached_x_min <= knobs.y_min]


def tag_legs(legs: list[Leg], seg: Segment, *, anchors: list[float], knobs: Knobs) -> list[dict]:
    """Spec §3b steps 3–5: nearest level at the origin, and what was said in
    the W minutes before it, in the leg's direction."""
    out: list[dict] = []
    for leg in legs:
        o = seg.bars[leg.origin_i]
        nearest, dist = None, None
        for a in anchors:
            d = abs(a - leg.origin_px)
            if dist is None or d < dist:
                nearest, dist = a, round(d, 2)
        since = o.t1 - timedelta(minutes=knobs.w_min)
        said: list[str] = []
        tag = "silent"
        for ev in seg.events:
            if ev.get("type") not in MEASURED_TYPES:
                continue
            k = seg.pos(ev.get("bar_i"))
            if k is None:
                continue
            t = seg.bars[k].t1
            if t < since or t > o.t1:
                continue
            if direction_of(ev) != leg.direction:
                continue
            said.append(f"{ev['type']}:{ev.get('state') or ''}@{t.strftime('%H:%M')}")
            if ev["type"] == "SetupRecognition" and ev.get("state") == "confirmed":
                tag = "called"
            elif tag != "called":
                tag = "hinted"
        out.append({
            "run": seg.run_no, "direction": leg.direction,
            "origin_bar": o.i, "origin_ct": o.t1.strftime("%H:%M"),
            "end_bar": seg.bars[leg.end_i].i, "end_ct": seg.bars[leg.end_i].t1.strftime("%H:%M"),
            "origin_px": leg.origin_px, "end_px": leg.end_px, "pts": leg.pts,
            "minutes": leg.minutes, "reached_x_min": leg.reached_x_min,
            "nearest_level": nearest, "level_distance": dist,
            "near_level": (dist is not None and dist <= knobs.z_pts),
            "tag": tag, "said_before": said,
        })
    return out
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py
git commit -m "postmortem: zigzag legs from highs/lows, keep by X-in-Y, tag called/hinted/silent against calls in the prior W minutes, nearest level at Z [co-7kgte]"
```

---

### Task 7: Mancini recap extraction and matching

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# ------------------------------------------------------------------ recap

RECAP = """On to today: Basic Themes
blah blah.
Trade Recap/Daily Summary
NOTE: The purpose of this trade recap section is to run down in greater detail previous examples of my three setup types that occurred within the last couple days.
The first high quality Failed Breakdown was the Failed Breakdown of 7777. I wrote yesterday at 2pm: "There is a safer Failed Breakdown just a little lower at 7777."
We recovered this shelf by 1:50PM, and I tweeted the long as well at 1:40PM: This was a classic, shallow Failed Breakdown not of a singular low, but a shelf at 7738.
Then a Level Reclaim of 7797 at 10:15AM which I did not take.
Trade Plan Wednesday
Supports are: 7777 (major), 7767.
"""


def test_extract_recap_rows():
    rows = pm.extract_recap(RECAP, letter_date=date(2026, 8, 18))
    setups = {(r["setup"], r["level"], r["time_et"]) for r in rows}
    assert ("failed_breakdown", 7777.0, None) in setups or \
        any(s == "failed_breakdown" and lv == 7777.0 for s, lv, _ in setups)
    assert ("failed_breakdown", 7738.0, "1:40PM") in setups
    assert ("level_reclaim", 7797.0, "10:15AM") in setups
    assert all(r["letter_date"] == "2026-08-18" and r["quote"] for r in rows)


def test_extract_recap_without_section_is_empty():
    assert pm.extract_recap("no recap here. Trade Plan Monday", letter_date=date(2026, 8, 18)) == []


def test_match_recap_tiers():
    calls = [
        {"type": "SetupRecognition", "state": "confirmed", "setup": "failed_breakdown",
         "anchor": 7738.0, "ct": "12:45", "direction": "bullish"},      # 1:40PM ET = 12:40 CT → Δ5 EXACT
        {"type": "SetupRecognition", "state": "confirmed", "setup": "level_reclaim",
         "anchor": 7777.0, "ct": "10:00", "direction": "bullish"},
    ]
    rows = [{"setup": "failed_breakdown", "level": 7738.0, "time_et": "1:40PM"},
            {"setup": "failed_breakdown", "level": 7777.0, "time_et": None},
            {"setup": "range_trap", "level": 7900.0, "time_et": "9:00AM"}]
    m = pm.match_recap(rows, calls)
    assert [x["tier"] for x in m] == ["EXACT", "LEVEL", "MISS"]
    assert m[0]["matched_ct"] == "12:45" and m[1]["matched_ct"] == "10:00"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k recap`
Expected: FAIL — `AttributeError: ... 'extract_recap'`

- [ ] **Step 3: Implement**

```python
# ------------------------------------------------------------------ recap

RECAP_START = "Trade Recap/Daily Summary"
RECAP_END = ("Trade Plan", "Unsubscribe")
SETUP_WORDS = (("failed breakdown", "failed_breakdown"),
               ("level reclaim", "level_reclaim"),
               ("range trap", "range_trap"))
FAMILY = {"failed_breakdown", "level_reclaim"}   # score_recognizer's sibling pair


def extract_recap(letter_text: str, *, letter_date: _date) -> list[dict]:
    """Spec §3c. Sentences of the recap section naming one of his three setup
    words with a four-digit level; the time, when the sentence has one.
    Plain text in (run the blob through runbook.mancini.clean.html_to_text
    first). Deterministic; no model."""
    from mancini.parser import extract_section, extract_time_anchor, split_sentences
    section = extract_section(letter_text, RECAP_START, list(RECAP_END))
    if not section:
        return []
    rows: list[dict] = []
    for s in split_sentences(section):
        low = s.lower()
        setup = next((code for word, code in SETUP_WORDS if word in low), None)
        if not setup:
            continue
        levels = [float(m) for m in re.findall(r"\b([5-9]\d{3})\b", s)]
        if not levels:
            continue
        t = extract_time_anchor(s) or None
        for lv in dict.fromkeys(levels):
            rows.append({"letter_date": letter_date.isoformat(), "setup": setup,
                         "level": lv, "time_et": t, "quote": s.strip()[:300]})
    return rows


def _minutes_ct(time_et: str | None) -> int | None:
    """Mancini writes ET; the record is CT (ET − 1h)."""
    if not time_et:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(AM|PM)", time_et)
    if not m:
        return None
    h, mn, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    return ((h % 12) + (12 if ap == "PM" else 0)) * 60 + mn - 60


def match_recap(rows: list[dict], calls: list[dict]) -> list[dict]:
    """score_recognizer's tiers over the day's confirmed setups:
    EXACT same setup at his level within 15 min; FAMILY the FBD/reclaim
    sibling within 30 min; LEVEL at his level but no time agreement; MISS."""
    rank = {"EXACT": 3, "FAMILY": 2, "LEVEL": 1, "MISS": 0}
    confirmed = [c for c in calls if c.get("type") == "SetupRecognition"
                 and c.get("state") == "confirmed" and c.get("anchor") is not None]
    out: list[dict] = []
    for r in rows:
        best = {"tier": "MISS", "matched_ct": None, "matched_setup": None}
        t_ct = _minutes_ct(r.get("time_et"))
        for c in confirmed:
            if abs(float(c["anchor"]) - float(r["level"])) > 2.0:
                continue
            hh, mm = c["ct"].split(":")
            dt = abs(int(hh) * 60 + int(mm) - t_ct) if t_ct is not None else None
            same = c.get("setup") == r["setup"]
            if dt is not None and dt <= 15 and same:
                tier = "EXACT"
            elif dt is not None and dt <= 30 and c.get("setup") in FAMILY and r["setup"] in FAMILY:
                tier = "FAMILY"
            else:
                tier = "LEVEL"
            if rank[tier] > rank[best["tier"]]:
                best = {"tier": tier, "matched_ct": c["ct"], "matched_setup": c.get("setup")}
        out.append(r | best)
    return out
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py
git commit -m "postmortem: recap extractor over the letter's Trade Recap section (three setup words, level, time) and score_recognizer's match tiers [co-7kgte]"
```

---

### Task 8: Flags, census, sessions, `analyze_day`

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# ----------------------------------------------------------- analyze_day

def test_session_of():
    assert pm.session_of(datetime(2026, 8, 18, 3, 0, tzinfo=CT)) == "overnight"
    assert pm.session_of(datetime(2026, 8, 18, 8, 30, tzinfo=CT)) == "cash"
    assert pm.session_of(datetime(2026, 8, 18, 14, 59, tzinfo=CT)) == "cash"
    assert pm.session_of(datetime(2026, 8, 18, 15, 0, tzinfo=CT)) == "evening"


def test_flags_rules():
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    calls = pm.measure_calls(seg, pm.Knobs())
    legs = [{"tag": "silent", "near_level": True, "pts": 7.0, "direction": "bullish",
             "origin_ct": "09:00", "origin_bar": 3, "nearest_level": 7720.0, "said_before": []}]
    cen = pm.census(seg, calls)
    flags = pm.flags(calls, legs, cen, session_range=20.0, knobs=pm.Knobs())
    kinds = {f["flag"] for f in flags}
    assert "late-confirm" in kinds and "silent-move" in kinds   # lag 2 bars / +3.75; silent near level
    assert "dense-anchor" not in kinds and "grid-density" not in kinds


def test_flags_dense_anchor_and_grid_density():
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(12)]
    events = [_ev(i, bars, setup="failed_breakdown", bias="bullish", anchor_price=99.0,
                  anchor_kind="support", state="confirmed", beats=[], fire_index=i + 1,
                  confidence=0.6) for i in range(6)]
    seg = _segment(bars, events, mancini=[99.0])
    calls = pm.measure_calls(seg, pm.Knobs())
    flags = pm.flags(calls, [], pm.census(seg, calls), session_range=5.0, knobs=pm.Knobs())
    assert {"dense-anchor", "grid-density"} <= {f["flag"] for f in flags}


def test_analyze_day_on_fixture_has_every_section_input():
    segs = pm.load_live_segments(FIXTURE)
    res = pm.analyze_day(segs, pm.Knobs(), day=date(2026, 8, 18), source="live",
                         pass_name="same-day", now=datetime(2026, 8, 18, 15, 30, tzinfo=CT))
    assert res["day"] == "2026-08-18" and res["source"] == "live" and res["pass"] == "same-day"
    assert res["runs"] == [{"run": 1, "started": segs[0].started, "bars": 3, "complete": True},
                           {"run": 2, "started": segs[1].started, "bars": 41, "complete": True}]
    assert res["coverage"]["first_ct"] and res["coverage"]["last_ct"]
    assert res["census"]["by_type"]["SetupRecognition"]["confirmed"] >= 1
    per = {a["anchor"]: a for a in res["census"]["per_anchor"]}
    assert 7720.0 in per and per[7720.0]["confirmed"] >= 1
    assert isinstance(res["calls"], list) and isinstance(res["legs"], list)
    assert all("session" in c for c in res["calls"])
    assert res["recap"] == {"status": "not-received", "rows": []}
    assert isinstance(res["flags"], list)
    assert res["knobs"] == _knobs_dict(pm.Knobs())
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k "analyze_day or flags or session_of"`
Expected: FAIL — `AttributeError: ... 'session_of'`

- [ ] **Step 3: Implement**

```python
# ------------------------------------------------------------- the day

def session_of(t: datetime) -> str:
    """overnight (before 08:30 CT) | cash (08:30–15:00) | evening (from 15:00)."""
    m = t.hour * 60 + t.minute
    if m < 8 * 60 + 30:
        return "overnight"
    if m < 15 * 60:
        return "cash"
    return "evening"


def census(seg: Segment, calls: list[dict]) -> dict:
    """Counts by type/state and per anchor (spec §4b.2)."""
    by_type: dict[str, dict[str, int]] = {}
    per: dict[float, dict] = {}
    for ev in seg.events:
        t = ev.get("type", "?")
        state = ev.get("state") or "-"
        by_type.setdefault(t, {}).setdefault(state, 0)
        by_type[t][state] += 1
        if t == "SetupRecognition" and ev.get("anchor_price") is not None:
            a = float(ev["anchor_price"])
            k = seg.pos(ev.get("bar_i"))
            ct = seg.bars[k].t1.strftime("%H:%M") if k is not None else None
            row = per.setdefault(a, {"anchor": a, "forming": 0, "confirmed": 0,
                                     "invalidated": 0, "first_ct": ct, "last_ct": ct})
            if state in row:
                row[state] += 1
            if ct:
                row["first_ct"] = min(row["first_ct"] or ct, ct)
                row["last_ct"] = max(row["last_ct"] or ct, ct)
    return {"by_type": by_type,
            "per_anchor": sorted(per.values(), key=lambda r: r["anchor"]),
            "n_calls_measured": len(calls)}


def merge_census(parts: list[dict]) -> dict:
    out = {"by_type": {}, "per_anchor": [], "n_calls_measured": 0}
    per: dict[float, dict] = {}
    for c in parts:
        for t, states in c["by_type"].items():
            for s, n in states.items():
                out["by_type"].setdefault(t, {}).setdefault(s, 0)
                out["by_type"][t][s] += n
        for r in c["per_anchor"]:
            if r["anchor"] not in per:
                per[r["anchor"]] = dict(r)
                continue
            row = per[r["anchor"]]
            for kf in ("forming", "confirmed", "invalidated"):
                row[kf] += r[kf]
            cts = [x for x in (row["first_ct"], r["first_ct"]) if x]
            row["first_ct"] = min(cts) if cts else None
            cts = [x for x in (row["last_ct"], r["last_ct"]) if x]
            row["last_ct"] = max(cts) if cts else None
        out["n_calls_measured"] += c["n_calls_measured"]
    out["per_anchor"] = sorted(per.values(), key=lambda r: r["anchor"])
    return out


def flags(calls: list[dict], legs: list[dict], cen: dict, *, session_range: float,
          knobs: Knobs) -> list[dict]:
    """Spec §3d. Each flag names the bar it points at."""
    out: list[dict] = []
    for a in cen["per_anchor"]:
        if a["confirmed"] >= knobs.dense_anchor_fires:
            out.append({"flag": "dense-anchor", "anchor": a["anchor"], "n": a["confirmed"],
                        "at": f"{a['first_ct']}–{a['last_ct']}",
                        "why": f"{a['confirmed']} confirmed fires on {a['anchor']:g}"})
    for c in calls:
        if c.get("state") != "confirmed":
            continue
        lb, lp = c.get("confirm_lag_bars"), c.get("confirm_lag_pts")
        if (lb is not None and lb >= knobs.late_confirm_bars) or \
           (lp is not None and lp >= knobs.late_confirm_pts):
            why = f"confirm {lb if lb is not None else '?'} bars after the reclaim"
            if lp is not None:
                why += f", {lp:+.2f} from {c['anchor']:g}"
            out.append({"flag": "late-confirm", "anchor": c["anchor"], "bar": c["bar_i"],
                        "at": c["ct"], "lag_bars": lb, "lag_pts": lp, "why": why})
    for l in legs:
        if l["tag"] == "silent" and l["near_level"]:
            out.append({"flag": "silent-move", "bar": l["origin_bar"], "at": l["origin_ct"],
                        "pts": l["pts"], "direction": l["direction"], "anchor": l["nearest_level"],
                        "why": f"{l['pts']:g} pts {l['direction']} from {l['origin_ct']} near "
                               f"{l['nearest_level']:g}, nothing said in the prior window"})
        if l["pts"] >= knobs.breakout_pts and l["near_level"] and l["tag"] != "called" and \
           l["said_before"] and all(s.startswith("SetupRecognition:invalidated") for s in l["said_before"]):
            out.append({"flag": "no-breakout-word", "bar": l["origin_bar"], "at": l["origin_ct"],
                        "pts": l["pts"], "direction": l["direction"], "anchor": l["nearest_level"],
                        "why": f"{l['pts']:g} pts through {l['nearest_level']:g} with only "
                               f"'invalidated' said about it"})
    n_conf = sum(1 for c in calls if c.get("state") == "confirmed")
    if session_range > 0:
        density = n_conf / (session_range / 10.0)
        if density >= knobs.grid_density:
            out.append({"flag": "grid-density", "n": n_conf, "range": session_range,
                        "per_10": round(density, 1),
                        "why": f"{n_conf} confirms over a {session_range:g}-pt range "
                               f"({density:.1f} per 10 pts)"})
    return out


def analyze_day(segments: list[Segment], knobs: Knobs, *, day: _date, source: str,
                pass_name: str, now: datetime, recap_rows: list[dict] | None = None,
                letter_status: str = "not-received") -> dict:
    """The whole day as one dict — the ``<day>.json`` of spec §4a."""
    calls: list[dict] = []
    legs: list[dict] = []
    cens: list[dict] = []
    lo = hi = None
    for seg in segments:
        c = measure_calls(seg, knobs)
        for row in c:
            row["session"] = session_of(datetime.fromisoformat(row["t1"]))
        calls += c
        anchors = set(seg.mancini) | {float(e["price"]) for e in seg.events
                                      if e.get("type") == "Level" and e.get("price") is not None}
        lg = tag_legs(keep_legs(zigzag_legs(seg.bars, knobs.x_pts), knobs), seg,
                      anchors=sorted(anchors), knobs=knobs)
        for row in lg:
            k = seg.pos(row["origin_bar"])
            row["session"] = session_of(seg.bars[k].t1) if k is not None else "?"
        legs += lg
        cens.append(census(seg, c))
        for b in seg.bars:
            lo = b.l if lo is None else min(lo, b.l)
            hi = b.h if hi is None else max(hi, b.h)
    cen = merge_census(cens) if cens else {"by_type": {}, "per_anchor": [], "n_calls_measured": 0}
    cash = [b for s in segments for b in s.bars if session_of(b.t1) == "cash"]
    cash_range = (max(b.h for b in cash) - min(b.l for b in cash)) if cash else 0.0
    spans = [s.span for s in segments if s.span]
    coverage = {
        "first_ct": min(s[0] for s in spans).strftime("%H:%M") if spans else None,
        "last_ct": max(s[1] for s in spans).strftime("%H:%M") if spans else None,
        "bars": sum(len(s.bars) for s in segments),
        "unmeasured_note": None,
    }
    if spans:
        last = max(s[1] for s in spans)
        if last.date() == now.date() and last < now - timedelta(minutes=30):
            coverage["unmeasured_note"] = (
                f"record ends {last.strftime('%H:%M')} CT; "
                f"{int((now - last).total_seconds() // 60)} minutes before the pass unmeasured")
    recap = {"status": letter_status, "rows": match_recap(recap_rows, calls) if recap_rows else []}
    return {
        "day": day.isoformat(), "source": source, "pass": pass_name,
        "generated_at": now.isoformat(),
        "bar_n": segments[0].bar_n if segments else None,
        "runs": [{"run": s.run_no, "started": s.started, "bars": len(s.bars),
                  "complete": s.complete} for s in segments],
        "anchors": sorted({a for s in segments for a in s.mancini}),
        "coverage": coverage,
        "range": {"low": lo, "high": hi, "cash": round(cash_range, 2)},
        "census": cen, "calls": calls, "legs": legs, "recap": recap,
        "flags": flags(calls, legs, cen, session_range=cash_range, knobs=knobs),
        "knobs": knobs_to_dict(knobs),
    }
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py
git commit -m "postmortem: census, sessions, the five flags, analyze_day — the <day>.json in one call [co-7kgte]"
```

---

### Task 9: Ledger I/O and history

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# ----------------------------------------------------------------- ledger

def _res(day, pass_name, n_calls=2, n_legs=1):
    return {"day": day, "pass": pass_name, "source": "live", "generated_at": "x",
            "calls": [{"bar_i": i, "state": "confirmed", "setup": "failed_breakdown",
                       "verdict30": "win" if i % 2 else "loss", "type": "SetupRecognition"}
                      for i in range(n_calls)],
            "legs": [{"tag": "silent", "near_level": True} for _ in range(n_legs)],
            "flags": [], "census": {"by_type": {}, "per_anchor": [], "n_calls_measured": n_calls}}


def test_write_ledger_replaces_same_day_and_pass(tmp_path):
    root = tmp_path / "pm"
    pm.write_ledger(_res("2026-08-18", "same-day", 2, 1), root)
    pm.write_ledger(_res("2026-08-18", "same-day", 3, 2), root)     # re-run: replaces
    pm.write_ledger(_res("2026-08-18", "next-morning", 1, 1), root) # other pass: adds
    pm.write_ledger(_res("2026-08-17", "same-day", 1, 0), root)
    rows = [json.loads(l) for l in (root / "ledger.jsonl").read_text().splitlines()]
    assert sum(1 for r in rows if r["day"] == "2026-08-18" and r["pass"] == "same-day") == 3
    assert sum(1 for r in rows if r["day"] == "2026-08-18" and r["pass"] == "next-morning") == 1
    assert all({"day", "pass", "source"} <= set(r) for r in rows)
    legs = [json.loads(l) for l in (root / "legs.jsonl").read_text().splitlines()]
    assert len(legs) == 2 + 1 + 0
    assert json.loads((root / "2026-08-18.json").read_text())["pass"] == "next-morning"


def test_history_prefers_latest_pass_per_day(tmp_path):
    root = tmp_path / "pm"
    pm.write_ledger(_res("2026-08-17", "same-day", 4, 2), root)
    pm.write_ledger(_res("2026-08-17", "next-morning", 5, 3), root)
    pm.write_ledger(_res("2026-08-18", "same-day", 2, 1), root)
    h = pm.history(root, days=20, before="2026-08-19")
    assert h["days"] == ["2026-08-17", "2026-08-18"]
    assert h["confirms_per_day"] == [5, 2]
    assert h["silent_legs_per_day"] == [3, 1]
    assert h["median_confirms"] == 3.5
    assert h["by_setup"]["failed_breakdown"]["win"] == 3 and h["by_setup"]["failed_breakdown"]["loss"] == 4
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k "ledger or history"`
Expected: FAIL — `AttributeError: ... 'write_ledger'`

- [ ] **Step 3: Implement**

```python
# ----------------------------------------------------------------- ledger

PASS_ORDER = {"backfill": 0, "same-day": 1, "next-morning": 2}


def _rewrite_jsonl(path: Path, keep, new_rows: list[dict]) -> None:
    """Replace rows failing ``keep`` with ``new_rows``; atomic via a temp file."""
    old: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("%s: unreadable line dropped", path.name)
                continue
            if keep(r):
                old.append(r)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in old + new_rows:
            fh.write(json.dumps(r, separators=(",", ":"), default=str) + "\n")
    tmp.replace(path)


def write_ledger(res: dict, root: Path = LEDGER_ROOT) -> dict:
    """``<day>.json`` (whole result, last writer wins), and one row per call /
    leg in ``ledger.jsonl`` / ``legs.jsonl`` — rows for this (day, pass)
    replaced, never duplicated. Returns the paths written."""
    root.mkdir(parents=True, exist_ok=True)
    day, pass_name, source = res["day"], res["pass"], res["source"]
    stamp = {"day": day, "pass": pass_name, "source": source}

    def keep(r: dict) -> bool:
        return not (r.get("day") == day and r.get("pass") == pass_name)

    _rewrite_jsonl(root / "ledger.jsonl", keep, [stamp | c for c in res["calls"]])
    _rewrite_jsonl(root / "legs.jsonl", keep, [stamp | l for l in res["legs"]])
    day_path = root / f"{day}.json"
    day_path.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return {"day_json": day_path, "ledger": root / "ledger.jsonl", "legs": root / "legs.jsonl"}


def history(root: Path = LEDGER_ROOT, *, days: int = 20, before: str | None = None) -> dict:
    """The last ``days`` session days strictly before ``before`` (ISO date),
    one pass per day (the latest in PASS_ORDER). Inputs for spec §4b.6."""
    calls_by_day: dict[str, dict[str, list[dict]]] = {}
    legs_by_day: dict[str, dict[str, list[dict]]] = {}
    for path, store in ((root / "ledger.jsonl", calls_by_day), (root / "legs.jsonl", legs_by_day)):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if before and r["day"] >= before:
                continue
            store.setdefault(r["day"], {}).setdefault(r["pass"], []).append(r)
    all_days = sorted(set(calls_by_day) | set(legs_by_day))[-days:]
    out = {"days": all_days, "confirms_per_day": [], "silent_legs_per_day": [],
           "by_setup": {}, "median_confirms": None, "median_silent": None}
    for d in all_days:
        cp, lp = calls_by_day.get(d, {}), legs_by_day.get(d, {})
        best = max(set(cp) | set(lp), key=lambda p: PASS_ORDER.get(p, -1))
        conf = [c for c in cp.get(best, []) if c.get("state") == "confirmed"]
        out["confirms_per_day"].append(len(conf))
        out["silent_legs_per_day"].append(
            sum(1 for l in lp.get(best, []) if l.get("tag") == "silent" and l.get("near_level")))
        for c in conf:
            s = out["by_setup"].setdefault(c.get("setup") or "?",
                                           {"win": 0, "loss": 0, "neither": 0, "both-in-one-bar": 0})
            v = c.get("verdict30") or "neither"
            s[v] = s.get(v, 0) + 1
    if all_days:
        out["median_confirms"] = statistics.median(out["confirms_per_day"])
        out["median_silent"] = statistics.median(out["silent_legs_per_day"])
    return out
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py
git commit -m "postmortem: ledger (<day>.json, ledger.jsonl, legs.jsonl; replace per day+pass) and last-N-days history [co-7kgte]"
```

---

### Task 10: The page (markdown)

**Files:**
- Modify: `market/orderflow/postmortem.py`
- Modify: `.gitignore` (if needed)
- Test: `tests/market/orderflow/test_postmortem.py`

- [ ] **Step 1: Write the failing tests**

```python
# ------------------------------------------------------------------- page

HEADINGS = ["## Census", "## Calls made", "## Moves", "## Mancini's recap",
            "## Last 20 days", "## For Strader", "## What this page does not judge"]


def test_render_page_has_every_section_and_the_footer():
    segs = pm.load_live_segments(FIXTURE)
    res = pm.analyze_day(segs, pm.Knobs(), day=date(2026, 8, 18), source="live",
                         pass_name="same-day", now=datetime(2026, 8, 18, 15, 30, tzinfo=CT))
    md = pm.render_page(res, pm.history(Path("/nonexistent"), days=20))
    assert md.startswith("# Day post-mortem — 2026-08-18")
    for h in HEADINGS:
        assert h in md, h
    assert "what you saw" in md                    # live source label
    assert "Mancini's recap: not yet received" in md
    assert "| 13:" in md                           # a cash-session call row
    assert "The numbers above are the record." in md


def test_render_page_replay_label_and_truncation_banner():
    segs = pm.load_live_segments(FIXTURE)
    res = pm.analyze_day(segs, pm.Knobs(), day=date(2026, 8, 18), source="replay",
                         pass_name="backfill", now=datetime(2026, 8, 18, 23, 0, tzinfo=CT))
    res["coverage"]["unmeasured_note"] = "record ends 13:35 CT; 565 minutes before the pass unmeasured"
    md = pm.render_page(res, pm.history(Path("/nonexistent")))
    assert "today's recognizer on that day's tape" in md
    assert "record ends 13:35 CT" in md
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q -k render_page`
Expected: FAIL — `AttributeError: ... 'render_page'`

- [ ] **Step 3: Implement**

```python
# ------------------------------------------------------------------- page

FOOTER = """## What this page does not judge

Whether any level deserved to be an anchor, whether a move was "a breakdown"
in a trader's sense, and whether any refinement is right. Those are Strader's,
with Steve. The numbers above are the record."""

SOURCE_LABEL = {"live": "what you saw — the feeder's own record",
                "replay": "today's recognizer on that day's tape — not what was on the screen"}


def _f(x, nd: int = 2) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        s = f"{x:.{nd}f}"
        return s.rstrip("0").rstrip(".") if "." in s else s
    return str(x)


def _call_row(c: dict, knobs: Knobs) -> str:
    what = c["type"] if c["type"] != "SetupRecognition" else f"{c['setup']} {c['state']}"
    if c.get("anchor") is not None:
        what += f" @ {_f(c['anchor'])}"
    nth = _f(c.get("fire_index")) if c["type"] == "SetupRecognition" else "—"
    cells = [c["ct"], f"{c['run']}:{c['bar_i']}", what, c["direction"], nth, _f(c.get("confidence"))]
    for w in knobs.windows_min:
        cell = f"+{_f(c.get(f'mfe{w}'))} / −{_f(c.get(f'mae{w}'))}"
        if c.get(f"truncated{w}"):
            cell += " (window truncated)"
        cells.append(cell)
    big = max(knobs.windows_min)
    cells.append(c.get(f"verdict{big}", "—"))
    btl = c.get("back_to_level_min")
    cells.append(f"{btl} min" if btl is not None else "—")
    lb, lp = c.get("confirm_lag_bars"), c.get("confirm_lag_pts")
    if lb is not None:
        cells.append(f"{lb} bars, {lp:+.2f}")
    elif lp is not None:
        cells.append(f"{lp:+.2f}")
    else:
        cells.append("—")
    return "| " + " | ".join(str(x) for x in cells) + " |"


def render_page(res: dict, hist: dict) -> str:
    knobs = knobs_from_dict(res["knobs"])
    day = res["day"]
    L: list[str] = [f"# Day post-mortem — {day}", ""]
    L.append(f"Source: **{SOURCE_LABEL.get(res['source'], res['source'])}**. Pass: {res['pass']}, "
             f"written {res['generated_at'][:16].replace('T', ' ')}.")
    cov, runs = res["coverage"], res["runs"]
    restarts = "" if len(runs) <= 1 else " — restarts at " + ", ".join(r["started"][11:16] for r in runs[1:])
    L.append(f"Record: {cov['first_ct'] or '?'} → {cov['last_ct'] or '?'} CT, {cov['bars']} bars of "
             f"{_f(res.get('bar_n'))} contracts; {len(runs)} run(s){restarts}. "
             f"Anchors in play: {len(res['anchors'])} Mancini levels.")
    if cov.get("unmeasured_note"):
        L += ["", f"**Note:** {cov['unmeasured_note']}."]
    if res.get("range", {}).get("cash"):
        L.append(f"Cash-session range: {_f(res['range']['cash'])} points "
                 f"({_f(res['range']['low'])}–{_f(res['range']['high'])} over the whole record).")
    L.append("")
    # census
    L += ["## Census", "", "| Type | State | Count |", "|---|---|---|"]
    for t, states in sorted(res["census"]["by_type"].items()):
        for s, n in sorted(states.items()):
            L.append(f"| {t} | {s} | {n} |")
    L += ["", "| Anchor | forming | confirmed | invalidated | first | last |", "|---|---|---|---|---|---|"]
    for a in res["census"]["per_anchor"]:
        L.append(f"| {_f(a['anchor'])} | {a['forming']} | {a['confirmed']} | {a['invalidated']} "
                 f"| {a['first_ct'] or '—'} | {a['last_ct'] or '—'} |")
    L.append("")
    # calls
    L += ["## Calls made", ""]
    hdr = ["Time CT", "Run:bar", "What it said", "Dir", "nth on level", "Conf"]
    hdr += [f"For / against at {w} min" for w in knobs.windows_min]
    hdr += [f"±{_f(knobs.target_pts)} first", "Back to level", "Confirm lag"]
    for sess in ("cash", "overnight", "evening"):
        rows = [c for c in res["calls"] if c.get("session") == sess]
        L += [f"### {sess.capitalize()} session — {len(rows)} measured call(s)", ""]
        if not rows:
            L += ["None.", ""]
            continue
        L.append("| " + " | ".join(hdr) + " |")
        L.append("|" + "---|" * len(hdr))
        L += [_call_row(c, knobs) for c in rows]
        L.append("")
    # legs
    L += ["## Moves", "",
          f"Legs of at least {_f(knobs.x_pts)} points that reached that inside {knobs.y_min} minutes. "
          f"\"Near a level\" is within {_f(knobs.z_pts)} points; \"said before\" looks back {knobs.w_min} minutes.",
          "", "| Start CT | End CT | Dir | Points | Minutes | Nearest level (dist) | Near | Said before | Tag |",
          "|---|---|---|---|---|---|---|---|---|"]
    for l in res["legs"]:
        said = ", ".join(l["said_before"]) if l["said_before"] else "nothing"
        L.append(f"| {l['origin_ct']} | {l['end_ct']} | {l['direction']} | {_f(l['pts'])} | {l['minutes']} "
                 f"| {_f(l['nearest_level'])} ({_f(l['level_distance'])}) | {'yes' if l['near_level'] else 'no'} "
                 f"| {said} | **{l['tag']}** |")
    if not res["legs"]:
        L.append("| — | — | — | — | — | — | — | — | — |")
    L.append("")
    # recap
    L += ["## Mancini's recap", ""]
    rc = res["recap"]
    if rc["status"] == "not-received":
        L.append("Mancini's recap: not yet received (filled by the next-morning pass).")
    elif rc["status"] == "no-recap-section":
        L.append("The letter arrived but has no Trade Recap section.")
    elif not rc["rows"]:
        L.append("The letter's recap names no setup with a level.")
    else:
        L += ["| His setup | Level | His time (ET) | Match | Machine call (CT) | His words |",
              "|---|---|---|---|---|---|"]
        for r in rc["rows"]:
            L.append(f"| {r['setup']} | {_f(r['level'])} | {r.get('time_et') or '—'} | **{r['tier']}** "
                     f"| {r.get('matched_ct') or '—'} {r.get('matched_setup') or ''} | {r['quote'][:160]} |")
    L.append("")
    # history
    L += [f"## Last {knobs.history_days} days", ""]
    n_conf_today = sum(1 for c in res["calls"] if c.get("state") == "confirmed")
    n_silent_today = sum(1 for l in res["legs"] if l["tag"] == "silent" and l["near_level"])
    if not hist.get("days"):
        L.append("No earlier days in the ledger yet.")
    else:
        L += [f"{len(hist['days'])} day(s) in the ledger ({hist['days'][0]} → {hist['days'][-1]}).", "",
              "| | Today | Median of the last days |", "|---|---|---|",
              f"| Confirmed setups | {n_conf_today} | {_f(hist['median_confirms'])} |",
              f"| Silent moves near a level | {n_silent_today} | {_f(hist['median_silent'])} |", "",
              f"| Setup | ±{_f(knobs.target_pts)} win | loss | neither | both in one bar |",
              "|---|---|---|---|---|"]
        for s, v in sorted(hist["by_setup"].items()):
            L.append(f"| {s} | {v.get('win', 0)} | {v.get('loss', 0)} | {v.get('neither', 0)} | {v.get('both-in-one-bar', 0)} |")
    L.append("")
    # flags
    L += ["## For Strader", ""]
    if not res["flags"]:
        L.append("No flag tripped today.")
    for f in res["flags"]:
        where = (f" (bar {f['bar']}, {f['at']})" if f.get("bar") is not None
                 else (f" ({f['at']})" if f.get("at") else ""))
        L.append(f"- **{f['flag']}**{where}: {f['why']}.")
    L += ["", FOOTER, ""]
    return "\n".join(L)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS.

- [ ] **Step 5: gitignore check**

Run: `git check-ignore -q data/measurement/acuity-run2-days.jsonl && echo ignored || echo tracked`. If `tracked`, append `data/measurement/postmortem/` to `.gitignore` and include it in the commit.

- [ ] **Step 6: Commit**

```bash
git add market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py .gitignore
git commit -m "postmortem: the page — header, census, calls by session, moves, recap, last-20-days, flags, the standing footer [co-7kgte]"
```

---

### Task 11: The CLI `scripts/postmortem_day.py` (live passes, publish, register)

**Files:**
- Create: `scripts/postmortem_day.py`
- Test: `tests/scripts/test_postmortem_day.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/scripts/test_postmortem_day.py
"""CLI wiring for the day post-mortem: which day, which pass, where it writes,
and that tests never reach the desk. [co-7kgte]"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "postmortem" / "2026-08-18-trimmed.jsonl"
CT = ZoneInfo("America/Chicago")


def _load():
    path = REPO_ROOT / "scripts" / "postmortem_day.py"
    spec = importlib.util.spec_from_file_location("postmortem_day", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_resolve_day_same_day_is_today_next_morning_is_previous_session():
    m = _load()
    now = datetime(2026, 8, 19, 15, 30, tzinfo=CT)            # a Wednesday
    assert m.resolve_day(None, "same-day", now) == date(2026, 8, 19)
    assert m.resolve_day(None, "next-morning", now) == date(2026, 8, 18)
    mon = datetime(2026, 8, 17, 8, 27, tzinfo=CT)
    assert m.resolve_day(None, "next-morning", mon) == date(2026, 8, 14)
    assert m.resolve_day("2026-08-11", "same-day", now) == date(2026, 8, 11)


def test_run_live_pass_writes_ledger_and_page_without_publishing(tmp_path, monkeypatch):
    m = _load()
    published = []
    monkeypatch.setattr(m, "publish", lambda *a, **k: published.append(a) or 0)
    rc = m.run_live_pass(day=date(2026, 8, 18), pass_name="same-day",
                         record=FIXTURE, root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 18, 15, 30, tzinfo=CT),
                         letter=None, publish_pages=False)
    assert rc == 0
    res = json.loads((tmp_path / "2026-08-18.json").read_text())
    assert res["pass"] == "same-day" and res["census"]["n_calls_measured"] >= 1
    assert (tmp_path / "pages" / "postmortem-2026-08-18.md").exists()
    assert (tmp_path / "pages" / "postmortem-latest.md").read_text() == \
        (tmp_path / "pages" / "postmortem-2026-08-18.md").read_text()
    assert published == []


def test_run_live_pass_without_record_writes_a_saying_so_page_and_exits_2(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "publish", lambda *a, **k: 0)
    rc = m.run_live_pass(day=date(2026, 8, 20), pass_name="same-day",
                         record=tmp_path / "absent.jsonl", root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 20, 15, 30, tzinfo=CT),
                         letter=None, publish_pages=False)
    assert rc == 2
    md = (tmp_path / "pages" / "postmortem-2026-08-20.md").read_text()
    assert "No feeder record for 2026-08-20" in md


def test_find_letter_for_session_picks_that_evenings_letter(tmp_path):
    m = _load()
    (tmp_path / "2026-08-18-185443.txt").write_text("<html>x</html>")
    (tmp_path / "2026-08-17-182204.txt").write_text("<html>y</html>")
    assert m.find_letter_for_session(date(2026, 8, 18), letters_dir=tmp_path).name == "2026-08-18-185443.txt"
    assert m.find_letter_for_session(date(2026, 8, 19), letters_dir=tmp_path) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/scripts/test_postmortem_day.py -q`
Expected: FAIL — `FileNotFoundError` loading the script.

- [ ] **Step 3: Write the CLI**

```python
#!/usr/bin/env python3
"""Day post-mortem — run it for a day, publish the page, keep the ledger. [co-7kgte]

Spec: docs/superpowers/specs/2026-08-19-day-postmortem-design.md. The measuring
lives in market/orderflow/postmortem.py; this file decides WHICH day, reads
the record, writes the ledger, renders through COO's desk-html.sh, and
registers the stable page once.

PASSES
    same-day      15:30 CT — the feeder's record so far today (the evening
                  session is still being written; the page says so).
    next-morning  08:27 CT — the previous session again, now with the evening
                  bars and Mancini's recap from that evening's letter.
    backfill      --backfill: every corpus day with ES tape, replay path,
                  ledger rows only plus one summary page.

USAGE
    .venv/bin/python scripts/postmortem_day.py                       # same-day, today
    .venv/bin/python scripts/postmortem_day.py --pass next-morning   # previous session
    .venv/bin/python scripts/postmortem_day.py --day 2026-08-18 --pass next-morning
    .venv/bin/python scripts/postmortem_day.py --backfill --workers 6
    .venv/bin/python scripts/postmortem_day.py --dry-run             # nothing written

EXIT CODES
    0 ran and wrote;  2 no record for the day (page written saying so);
    3 renderer missing (ledger written, page not rendered);  1 anything else.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.corpus.paths import central_date, most_recent_session_day   # noqa: E402
from market.orderflow import postmortem as pm                           # noqa: E402
from market.orderflow.anchors import mancini_levels_for                 # noqa: E402
from market.orderflow.replay import has_es_day                          # noqa: E402
from market.orderflow.run_log import run_log_path                       # noqa: E402

logger = logging.getLogger("postmortem_day")
CT = ZoneInfo("America/Chicago")

DESK_HTML = Path("/root/projects/COO/tmuxMOO/bin/desk-html.sh")
DESK_REGISTER = Path("/root/projects/COO/tmuxMOO/bin/desk-register.sh")
DESK_DIR = Path("/var/moo/desk")
LETTERS_DIR = REPO_ROOT / "data" / "mancini-letters"


# ------------------------------------------------------------------ which day

def resolve_day(arg: str | None, pass_name: str, now: datetime) -> _date:
    if arg:
        return _date.fromisoformat(arg)
    if pass_name == "same-day":
        return central_date(now)
    return most_recent_session_day(now)


# --------------------------------------------------------------------- letter

def find_letter_for_session(day: _date, *, letters_dir: Path = LETTERS_DIR) -> Path | None:
    """The letter written the evening of ``day`` (it recaps that session).
    Files are <date>-<hhmmss>.txt; take the latest of that date."""
    hits = sorted(letters_dir.glob(f"{day.isoformat()}-*.txt"))
    return hits[-1] if hits else None


def recap_rows_for(day: _date, root: Path, letter: Path | None) -> tuple[str, list[dict]]:
    """(status, rows). Writes recaps/<letter-date>.json when a letter exists."""
    if letter is None:
        return "not-received", []
    from runbook.mancini.clean import html_to_text, looks_like_html
    raw = letter.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(raw) if looks_like_html(raw) else raw
    if pm.RECAP_START not in text:
        return "no-recap-section", []
    rows = pm.extract_recap(text, letter_date=day)
    out = root / "recaps"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{day.isoformat()}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return "received", rows


# -------------------------------------------------------------------- publish

def write_pages(root: Path, day: _date, md: str) -> tuple[Path, Path]:
    pages = root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    p = pages / f"postmortem-{day.isoformat()}.md"
    latest = pages / "postmortem-latest.md"
    p.write_text(md, encoding="utf-8")
    shutil.copyfile(p, latest)
    return p, latest


def publish(md_path: Path, html_name: str, *, also_latest: bool) -> int:
    """Render through desk-html.sh to /var/moo/desk/<html_name>; copy to the
    stable 'latest' page; register the latest .md once (idempotent). Returns
    0, or 3 when the renderer is absent/failed (the ledger still stands)."""
    if not DESK_HTML.exists():
        logger.warning("desk-html.sh absent at %s — page not rendered", DESK_HTML)
        return 3
    target = DESK_DIR / html_name
    try:
        proc = subprocess.run([str(DESK_HTML), str(md_path), str(target)],
                              capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("desk-html.sh failed to run: %s", e)
        return 3
    if proc.returncode != 0:
        logger.warning("desk-html.sh rc=%d: %s", proc.returncode, proc.stderr.strip()[:300])
        return 3
    logger.info("page: %s", target)
    if also_latest:
        shutil.copyfile(target, DESK_DIR / "desk-postmortem-latest.html")
        latest_md = md_path.parent / "postmortem-latest.md"
        try:
            out = subprocess.run([str(DESK_REGISTER), "Trading", str(latest_md)],
                                 capture_output=True, text=True, timeout=30)
            if out.returncode:
                logger.warning("desk-register rc=%d: %s", out.returncode, out.stderr.strip()[:200])
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("desk-register skipped: %s", e)
    return 0


# ----------------------------------------------------------------- live pass

def run_live_pass(*, day: _date, pass_name: str, record: Path, root: Path,
                  knobs: pm.Knobs, now: datetime, letter: Path | None,
                  publish_pages: bool) -> int:
    if not record.exists():
        md = (f"# Day post-mortem — {day.isoformat()}\n\n"
              f"**No feeder record for {day.isoformat()}** at `{record}`. Nothing to measure. "
              f"If the feeder ran, its run log was disabled (`--no-run-log`) or written elsewhere.\n")
        p, _ = write_pages(root, day, md)
        if publish_pages:
            publish(p, f"desk-postmortem-{day.isoformat()}.html", also_latest=True)
        logger.error("no feeder record for %s at %s", day, record)
        return 2
    segs = pm.load_live_segments(record)
    if pass_name == "next-morning":
        status, rows = recap_rows_for(day, root, letter)
    else:
        status, rows = "not-received", []
    res = pm.analyze_day(segs, knobs, day=day, source="live", pass_name=pass_name, now=now,
                         recap_rows=rows, letter_status=status)
    pm.write_ledger(res, root)
    hist = pm.history(root, days=knobs.history_days, before=day.isoformat())
    md = pm.render_page(res, hist)
    p, _ = write_pages(root, day, md)
    logger.info("%s %s: %d calls, %d legs, %d flags, recap %s", day, pass_name,
                len(res["calls"]), len(res["legs"]), len(res["flags"]), status)
    if publish_pages:
        return publish(p, f"desk-postmortem-{day.isoformat()}.html", also_latest=True)
    return 0


# ------------------------------------------------------------------ backfill
# (filled in by Task 12 — leave this comment as the anchor for it)


# ------------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", help="YYYY-MM-DD (default: today for same-day, previous session otherwise)")
    ap.add_argument("--pass", dest="pass_name", default="same-day",
                    choices=("same-day", "next-morning"))
    ap.add_argument("--backfill", action="store_true", help="replay every corpus day with ES tape")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--config", default=str(pm.CONFIG_PATH))
    ap.add_argument("--root", default=str(pm.LEDGER_ROOT))
    ap.add_argument("--no-publish", action="store_true", help="write ledger and .md, no desk page")
    ap.add_argument("--dry-run", action="store_true", help="resolve and report; write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    knobs = pm.load_knobs(Path(args.config))
    root = Path(args.root)
    now = datetime.now(tz=CT)
    if args.backfill:
        return run_backfill(root=root, knobs=knobs, workers=args.workers,
                            publish_pages=not args.no_publish, dry_run=args.dry_run)
    day = resolve_day(args.day, args.pass_name, now)
    record = run_log_path(day)
    letter = find_letter_for_session(day) if args.pass_name == "next-morning" else None
    if args.dry_run:
        print(f"would run {args.pass_name} for {day}: record {record} "
              f"({'present' if record.exists() else 'ABSENT'}), letter {letter or 'none'}, "
              f"ledger {root}, knobs {knobs}")
        return 0
    return run_live_pass(day=day, pass_name=args.pass_name, record=record, root=root,
                         knobs=knobs, now=now, letter=letter, publish_pages=not args.no_publish)


if __name__ == "__main__":
    sys.exit(main())
```

Until Task 12, `--backfill` raises `NameError: run_backfill` — acceptable for one commit; the tests here do not exercise it. `mancini_levels_for`, `has_es_day` and `timedelta` are imported now for Task 12.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/scripts/test_postmortem_day.py tests/market/orderflow/test_postmortem.py -q`
Expected: all PASS. Then a real dry run: `.venv/bin/python scripts/postmortem_day.py --day 2026-08-18 --pass next-morning --dry-run` → prints `record ... (present), letter .../2026-08-18-185443.txt`.

- [ ] **Step 5: A real run against the real 08-18 record, no publish**

Run: `.venv/bin/python scripts/postmortem_day.py --day 2026-08-18 --pass next-morning --no-publish --root /tmp/claude-0/-root-projects-COO/bcf51ff8-9257-4ce7-b165-b95e52641511/scratchpad/pm-test`
Expected: exit 0; a log line with calls/legs/flags counts; read `pages/postmortem-2026-08-18.md` and check the 13:18 confirm row shows `2 bars, +3.75` in the confirm-lag column and the recap section shows rows (the 08-18 letter names 7777 and 7738). If the counts look wrong, stop and fix before Task 12.

- [ ] **Step 6: Commit**

```bash
git add scripts/postmortem_day.py tests/scripts/test_postmortem_day.py
git commit -m "postmortem_day: CLI for the same-day and next-morning passes — resolve the day, recap from the evening's letter, ledger, page via desk-html.sh, register once [co-7kgte]"
```

---

### Task 12: Backfill over every tape day + summary page

**Files:**
- Modify: `scripts/postmortem_day.py`
- Modify: `market/orderflow/postmortem.py` (add `backfill_summary`, `render_backfill_page`)
- Test: `tests/market/orderflow/test_postmortem.py`, `tests/scripts/test_postmortem_day.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/market/orderflow/test_postmortem.py`:

```python
# --------------------------------------------------------------- backfill

def test_backfill_summary_distributions():
    days = [
        {"day": "2026-08-01", "status": "ok", "n_confirmed": 10, "n_legs": 4, "n_silent_near": 1,
         "legs_at": {"4": 9, "6": 4, "8": 2}, "by_setup": {"failed_breakdown": {"win": 4, "loss": 3}}},
        {"day": "2026-08-04", "status": "ok", "n_confirmed": 20, "n_legs": 6, "n_silent_near": 3,
         "legs_at": {"4": 12, "6": 6, "8": 3}, "by_setup": {"failed_breakdown": {"win": 8, "loss": 9}}},
        {"day": "2026-08-05", "status": "empty-tape"},
    ]
    s = pm.backfill_summary(days, pm.Knobs())
    assert s["n_days"] == 2 and len(s["skipped"]) == 1
    assert s["confirmed_per_day"]["median"] == 15
    assert s["legs_per_day_at"]["6"]["median"] == 5
    assert s["by_setup"]["failed_breakdown"] == {"win": 12, "loss": 12}
    md = pm.render_backfill_page(s)
    assert md.startswith("# Day post-mortem — backfill") and "| 6 |" in md and "2026-08-05" in md
```

Append to `tests/scripts/test_postmortem_day.py`:

```python
def test_backfill_one_day_worker_returns_summary_row(tmp_path, monkeypatch):
    m = _load()
    segs = m.pm.load_live_segments(FIXTURE)     # stand in for the replay
    monkeypatch.setattr(m.pm, "segments_from_replay", lambda day, *, bar_n, mancini: segs)
    monkeypatch.setattr(m, "mancini_levels_for", lambda day: [7720.0, 7724.0])
    row = m.backfill_one(date(2026, 8, 18), root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 19, 0, 0, tzinfo=CT))
    assert row["day"] == "2026-08-18" and row["status"] == "ok"
    assert row["n_confirmed"] >= 1 and set(row["legs_at"]) == {"4", "6", "8"}
    rows = [json.loads(l) for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert rows and all(r["pass"] == "backfill" and r["source"] == "replay" for r in rows)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py tests/scripts/test_postmortem_day.py -q -k backfill`
Expected: FAIL — `AttributeError: ... 'backfill_summary'`

- [ ] **Step 3: Implement the summary in the module**

Append to `market/orderflow/postmortem.py`:

```python
# --------------------------------------------------------------- backfill

def _dist(vals: list) -> dict:
    if not vals:
        return {"n": 0, "median": None, "p10": None, "p90": None, "max": None}
    s = sorted(vals)

    def q(p: float):
        return s[min(len(s) - 1, int(p * (len(s) - 1)))]

    return {"n": len(s), "median": statistics.median(s), "p10": q(0.1), "p90": q(0.9), "max": s[-1]}


def backfill_summary(day_rows: list[dict], knobs: Knobs) -> dict:
    """Distributions over the backfilled days (spec §6): calls per day, ±target
    outcomes by setup, legs per day at X and its two neighbours, silent-near-
    level legs per day."""
    ok = [r for r in day_rows if r.get("status") == "ok"]
    legs_at: dict[str, list[int]] = {}
    by_setup: dict[str, dict[str, int]] = {}
    for r in ok:
        for k, v in r.get("legs_at", {}).items():
            legs_at.setdefault(k, []).append(v)
        for s, v in r.get("by_setup", {}).items():
            t = by_setup.setdefault(s, {})
            for kk, n in v.items():
                t[kk] = t.get(kk, 0) + n
    return {
        "n_days": len(ok), "skipped": [r for r in day_rows if r.get("status") != "ok"],
        "first": ok[0]["day"] if ok else None, "last": ok[-1]["day"] if ok else None,
        "confirmed_per_day": _dist([r["n_confirmed"] for r in ok]),
        "legs_per_day_at": {k: _dist(v) for k, v in sorted(legs_at.items(), key=lambda kv: float(kv[0]))},
        "silent_near_per_day": _dist([r["n_silent_near"] for r in ok]),
        "by_setup": by_setup,
        "knobs": knobs_to_dict(knobs),
    }


def render_backfill_page(s: dict) -> str:
    k = s["knobs"]
    L = ["# Day post-mortem — backfill", "",
         f"{s['n_days']} tape days, {s['first']} → {s['last']}, today's recognizer on each "
         f"day's tape (not what was on the screen). Skipped: {len(s['skipped'])}.", "",
         "## Confirmed setups per day", "",
         "| n | median | 10th pct | 90th pct | max |", "|---|---|---|---|---|"]
    d = s["confirmed_per_day"]
    L.append(f"| {d['n']} | {_f(d['median'])} | {_f(d['p10'])} | {_f(d['p90'])} | {_f(d['max'])} |")
    L += ["", "## Legs per day at each X (points)", "",
          "| X | median | 10th pct | 90th pct | max |", "|---|---|---|---|---|"]
    for x, d in s["legs_per_day_at"].items():
        L.append(f"| {x} | {_f(d['median'])} | {_f(d['p10'])} | {_f(d['p90'])} | {_f(d['max'])} |")
    d = s["silent_near_per_day"]
    L += ["", f"## Silent moves near a level per day (X={_f(float(k['x_pts']))}, Z={_f(float(k['z_pts']))})", "",
          "| median | 10th pct | 90th pct | max |", "|---|---|---|---|",
          f"| {_f(d['median'])} | {_f(d['p10'])} | {_f(d['p90'])} | {_f(d['max'])} |", "",
          f"## ±{_f(float(k['target_pts']))} first touch by setup (30 min)", "",
          "| Setup | win | loss | neither | both in one bar |", "|---|---|---|---|---|"]
    for setup, v in sorted(s["by_setup"].items()):
        L.append(f"| {setup} | {v.get('win', 0)} | {v.get('loss', 0)} | {v.get('neither', 0)} | {v.get('both-in-one-bar', 0)} |")
    if s["skipped"]:
        L += ["", "## Skipped days", ""] + [f"- {r['day']}: {r.get('status')}" for r in s["skipped"]]
    L += ["", FOOTER, ""]
    return "\n".join(L)
```

- [ ] **Step 4: Implement the backfill in the CLI**

In `scripts/postmortem_day.py`, replace the `# (filled in by Task 12 …)` comment under `# ---- backfill` with:

```python
BACKFILL_BAR_N = 2000
BACKFILL_START = _date(2025, 5, 27)


def corpus_days_with_tape(start: _date = BACKFILL_START, end: _date | None = None) -> list[_date]:
    end = end or central_date(datetime.now(tz=CT))
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5 and has_es_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def backfill_one(day: _date, *, root: Path, knobs: pm.Knobs, now: datetime) -> dict:
    """One day through the replay path: ledger rows + a summary row. Never
    raises — a bad day is a row with a status, so the pool finishes."""
    try:
        mancini = mancini_levels_for(day)
        segs = pm.segments_from_replay(day, bar_n=BACKFILL_BAR_N, mancini=mancini)
        if not segs:
            return {"day": day.isoformat(), "status": "empty-tape"}
        res = pm.analyze_day(segs, knobs, day=day, source="replay", pass_name="backfill", now=now)
        pm.write_ledger(res, root)
        legs_at = {}
        for x in (knobs.x_pts - 2, knobs.x_pts, knobs.x_pts + 2):
            k2 = pm.replace(knobs, x_pts=x)
            legs_at[f"{x:g}"] = sum(len(pm.keep_legs(pm.zigzag_legs(seg.bars, x), k2)) for seg in segs)
        by_setup: dict[str, dict[str, int]] = {}
        big = max(knobs.windows_min)
        for c in res["calls"]:
            if c.get("state") != "confirmed":
                continue
            t = by_setup.setdefault(c.get("setup") or "?", {})
            v = c.get(f"verdict{big}") or "neither"
            t[v] = t.get(v, 0) + 1
        return {"day": day.isoformat(), "status": "ok",
                "n_confirmed": sum(1 for c in res["calls"] if c.get("state") == "confirmed"),
                "n_legs": len(res["legs"]),
                "n_silent_near": sum(1 for l in res["legs"] if l["tag"] == "silent" and l["near_level"]),
                "legs_at": legs_at, "by_setup": by_setup, "n_flags": len(res["flags"])}
    except Exception as e:  # noqa: BLE001 — one bad day must not sink 300
        logger.exception("backfill %s failed", day)
        return {"day": day.isoformat(), "status": f"error: {type(e).__name__}: {e}"[:200]}


def _bf_worker(args: tuple) -> dict:
    day_s, root_s, knobs_d, now_s = args
    logging.basicConfig(level=logging.WARNING)
    return backfill_one(_date.fromisoformat(day_s), root=Path(root_s),
                        knobs=pm.knobs_from_dict(knobs_d), now=datetime.fromisoformat(now_s))


def run_backfill(*, root: Path, knobs: pm.Knobs, workers: int, publish_pages: bool,
                 dry_run: bool) -> int:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    days = corpus_days_with_tape()
    print(f"backfill: {len(days)} tape days {days[0] if days else '-'} → {days[-1] if days else '-'}, "
          f"{workers} workers, ledger {root}")
    if dry_run or not days:
        return 0
    now = datetime.now(tz=CT)
    # each worker writes its own ledger shard; merged below (the jsonl rewrite
    # is not safe under concurrent writers)
    shards = root / "_shards"
    shards.mkdir(parents=True, exist_ok=True)
    jobs = [(d.isoformat(), str(shards / d.isoformat()), pm.knobs_to_dict(knobs), now.isoformat())
            for d in days]
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_bf_worker, j) for j in jobs]
        for n, f in enumerate(as_completed(futs), start=1):
            r = f.result()
            rows.append(r)
            if n % 25 == 0 or r["status"] != "ok":
                print(f"  {n}/{len(days)} {r['day']} {r['status']}")
    rows.sort(key=lambda r: r["day"])
    for r in rows:                      # merge shards, replace-by-day+pass
        shard = shards / r["day"] / f"{r['day']}.json"
        if shard.exists():
            pm.write_ledger(json.loads(shard.read_text()), root)
    shutil.rmtree(shards, ignore_errors=True)
    (root / "backfill-days.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    summary = pm.backfill_summary(rows, knobs)
    pages = root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    p = pages / "postmortem-backfill.md"
    p.write_text(pm.render_backfill_page(summary), encoding="utf-8")
    print(f"backfill: {summary['n_days']} ok, {len(summary['skipped'])} skipped; summary {p}")
    if publish_pages:
        return publish(p, "desk-postmortem-backfill.html", also_latest=False)
    return 0
```

`pm.replace` is `dataclasses.replace`, already imported in the module; `pm.knobs_to_dict` / `pm.knobs_from_dict` are from Task 2.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py tests/scripts/test_postmortem_day.py -q`
Expected: all PASS.

- [ ] **Step 6: Time one real backfill day, then run the whole thing**

Run:
```bash
time .venv/bin/python -c "
import sys, importlib.util; sys.path.insert(0,'.')
from pathlib import Path; from datetime import date, datetime; from zoneinfo import ZoneInfo
spec=importlib.util.spec_from_file_location('pd','scripts/postmortem_day.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.backfill_one(date(2026,8,11), root=Path('/tmp/claude-0/-root-projects-COO/bcf51ff8-9257-4ce7-b165-b95e52641511/scratchpad/pm-bf'), knobs=m.pm.Knobs(), now=datetime.now(tz=ZoneInfo('America/Chicago'))))"
```
Expected: a row with `status: ok` in well under a minute. Then the full run, in the background with a log:

`nohup .venv/bin/python scripts/postmortem_day.py --backfill --workers 6 > logs/postmortem-backfill.log 2>&1 &`

Expected when done (`tail -3 logs/postmortem-backfill.log`): `backfill: N ok, M skipped; summary …` and `/var/moo/desk/desk-postmortem-backfill.html` present. Record N, M, and the three legs-per-day medians on the bead (`bd update co-7kgte --append-notes "..."`).

- [ ] **Step 7: Commit**

```bash
git add scripts/postmortem_day.py market/orderflow/postmortem.py tests/market/orderflow/test_postmortem.py tests/scripts/test_postmortem_day.py
git commit -m "postmortem: --backfill over every tape day through the replay path (worker shards merged into the ledger), distributions summary page for setting the knobs [co-7kgte]"
```

---

### Task 13: Cron wrapper, SCHEDULE.md entries, acuity_run2 reuse

**Files:**
- Create: `scripts/cron/postmortem-wrapper.sh`
- Modify: `scripts/acuity_run2.py:85-104` and its one call site
- Modify: `market/orderflow/postmortem.py` (add `excursion_from_trades`)
- Modify: `/root/projects/COO/SCHEDULE.md` (json block)

- [ ] **Step 1: Write the wrapper**

```bash
#!/usr/bin/env bash
# postmortem-wrapper.sh — the day post-mortem, two passes. [co-7kgte]
#
#   30 15 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/postmortem-wrapper.sh same-day
#   27 8  * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/postmortem-wrapper.sh next-morning
#
# WHY TWO PASSES. At 15:30 the feeder is still writing the evening session into
# the same day file; the same-day page measures what is there and says so. At
# 08:27 the previous session is complete and that evening's Mancini letter has
# been parsed (08:15), so the morning pass re-measures the whole day and adds
# his recap. 08:27 keeps its own minute: 08:15 parse, 08:20 tracker, 08:25 risk.
#
# MORNING SMOKE. Before the next-morning pass, the previous session's
# <day>.json from its 15:30 pass must exist and parse; if not, that is an
# alert in its own right (the same-day cron did not run or died), and the pass
# still runs so the day is not lost.
#
# FAILURE. Non-zero exit → corpus_daily.emit_alert("postmortem", …) so it
# lands in the health log the morning heartbeat reads. rc=2 (no record) and
# rc=3 (renderer missing; ledger written) are distinguishable there.
#
# PATH IS SET EXPLICITLY — cron's minimal PATH [st-i68].
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

PASS="${1:-same-day}"
REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
LOG="${STRADER_LOG_DIR:-$REPO/logs}/postmortem.log"
mkdir -p "$(dirname "$LOG")"

alert() {  # $1 message, $2 pass, $3 rc
    PM_MSG="$1" PM_PASS="$2" PM_RC="$3" PYTHONPATH="$REPO" "$PY" - <<'PYEOF' || echo "WARN: alert emission failed"
import os, sys
sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert
emit_alert("postmortem", os.environ["PM_MSG"],
           {"pass": os.environ["PM_PASS"], "returncode": int(os.environ["PM_RC"])})
PYEOF
}

{
    echo "=== postmortem $PASS start $(date +%Y-%m-%dT%H:%M:%S%z) ==="
    if [[ ! -x "$PY" ]]; then echo "FATAL: venv python not executable: $PY"; exit 1; fi
    cd "$REPO" || { echo "FATAL: repo dir missing: $REPO"; exit 1; }

    if [[ "$PASS" == "next-morning" ]]; then
        PREV=$(PYTHONPATH="$REPO" "$PY" -c 'from market.corpus.paths import most_recent_session_day; print(most_recent_session_day())')
        if ! PYTHONPATH="$REPO" "$PY" -c "import json; json.load(open('data/measurement/postmortem/$PREV.json'))" 2>/dev/null; then
            echo "SMOKE: data/measurement/postmortem/$PREV.json missing or unreadable — the 15:30 pass did not land"
            alert "same-day post-mortem for $PREV never landed (no <day>.json); the morning pass is running anyway" smoke 0
        fi
    fi

    PYTHONPATH="$REPO" "$PY" "$REPO/scripts/postmortem_day.py" --pass "$PASS"
    rc=$?
    echo "=== postmortem $PASS end $(date +%Y-%m-%dT%H:%M:%S%z) (rc=$rc) ==="
    if (( rc != 0 )); then
        case $rc in
            2) why="no feeder record for the day (page written saying so)" ;;
            3) why="desk renderer missing or failed — ledger written, page not rendered" ;;
            *) why="unexpected failure; see logs/postmortem.log" ;;
        esac
        alert "day post-mortem $PASS pass rc=$rc: $why" "$PASS" "$rc"
    fi
    exit $rc
} >> "$LOG" 2>&1
```

`chmod +x scripts/cron/postmortem-wrapper.sh`. Smoke it by hand: `scripts/cron/postmortem-wrapper.sh next-morning; tail -5 logs/postmortem.log` → expect the `end ... (rc=0)` line, `/var/moo/desk/desk-postmortem-<previous session>.html` present, and `desk-postmortem-latest.html` beside it. Open the latest page and read it once, top to bottom, against spec §4b.

- [ ] **Step 2: acuity_run2 imports the shared trade-level excursion**

Append to `market/orderflow/postmortem.py`:

```python
def excursion_from_trades(trades: list, start_i: int, entry: float, sign: int,
                          until: datetime, *, target: float = 5.0) -> tuple[float, float, str]:
    """Trade-level twin of ``excursion`` (moved from scripts/acuity_run2.py,
    numbers unchanged): MFE, MAE and first-touch verdict from trades[start_i:]
    until ``until``."""
    mfe = mae = 0.0
    verdict = "neither"
    for t in trades[start_i:]:
        if t.ts > until:
            break
        ex = sign * (t.price - entry)
        if ex > mfe:
            mfe = ex
        if -ex > mae:
            mae = -ex
        if verdict == "neither":
            if ex >= target:
                verdict = "win"
            elif ex <= -target:
                verdict = "loss"
    return mfe, mae, verdict
```

In `scripts/acuity_run2.py`: delete `def _excursion(...)` (lines 85–104), add `from market.orderflow.postmortem import excursion_from_trades  # noqa: E402` beside the other `market.orderflow` imports, and change the one call `_excursion(trades, i, entry, sign, r.timestamp + timedelta(minutes=w))` to `excursion_from_trades(trades, i, entry, sign, r.timestamp + timedelta(minutes=w), target=TARGET_PTS)`.

Verify: `.venv/bin/python -c "import ast; ast.parse(open('scripts/acuity_run2.py').read()); print('ok')"` and `.venv/bin/python scripts/acuity_run2.py --days 2026-08-11 --workers 1` completes (it appends a run block to its own outputs — normal; mention the run in the commit message).

- [ ] **Step 3: SCHEDULE.md entries (COO repo)**

In `/root/projects/COO/SCHEDULE.md`, inside the json block, after the `strader-level-tracker` entry add:

```json
  {
    "id": "strader-postmortem-morning",
    "owner": "Strader",
    "host": "Zgent",
    "surface": "cron",
    "schedule": "27 8 * * 1-5",
    "command": "/usr/bin/bash /root/projects/Strader/scripts/cron/postmortem-wrapper.sh next-morning",
    "purpose": "Day post-mortem, next-morning pass: the previous session re-measured with its evening bars and Mancini's recap from the 08:15 parse; page desk-postmortem-<day>.html and -latest.html.",
    "heartbeat": null,
    "depends_on": [
      "strader-mancini-preopen"
    ],
    "bead": "co-7kgte",
    "comment": [
      "# Day post-mortem, morning pass [co-7kgte]. After the 08:15 parse; its own minute (08:20 tracker, 08:25 risk)."
    ]
  },
```

and next to the last afternoon Strader entry:

```json
  {
    "id": "strader-postmortem-close",
    "owner": "Strader",
    "host": "Zgent",
    "surface": "cron",
    "schedule": "30 15 * * 1-5",
    "command": "/usr/bin/bash /root/projects/Strader/scripts/cron/postmortem-wrapper.sh same-day",
    "purpose": "Day post-mortem, same-day pass: what the recognizer called today, what followed, the moves nothing called; ledger data/measurement/postmortem/, page desk-postmortem-<day>.html.",
    "heartbeat": null,
    "depends_on": [],
    "bead": "co-7kgte",
    "comment": [
      "# Day post-mortem, same-day pass [co-7kgte]. Cash close 15:00; the feeder keeps writing the evening session — the page says what it measured."
    ]
  },
```

Then, from `/root/projects/COO`: `bash factory/scripts/schedule-check.sh` (expect the two new entries reported as missing from the crontab), then `bash factory/scripts/schedule-generate.sh --install` (backs up, installs, reads back), then `crontab -l | grep postmortem` → two lines. If the generator refuses or reports an unrecognised live entry, stop and read its output; do not hand-edit the crontab.

- [ ] **Step 4: Commit (both repos)**

```bash
# Strader
git add scripts/cron/postmortem-wrapper.sh scripts/acuity_run2.py market/orderflow/postmortem.py
git commit -m "postmortem: cron wrapper (same-day 15:30, next-morning 08:27 with the morning smoke, emit_alert on failure); acuity_run2 imports excursion_from_trades [co-7kgte]"
# COO
cd /root/projects/COO && git add SCHEDULE.md && git commit -m "schedule: strader-postmortem-close 15:30 and strader-postmortem-morning 08:27 catalogued and installed [co-7kgte]" -- SCHEDULE.md
```

---

### Task 14: Land it — inbox row, spec status, push, bead

**Files:**
- Modify: `docs/a2a/inbox.md`
- Modify: `docs/superpowers/specs/2026-08-19-day-postmortem-design.md` (one status line)

- [ ] **Step 1: Full test run**

Run: `.venv/bin/python -m pytest tests/market/orderflow/test_postmortem.py tests/scripts/test_postmortem_day.py tests/market/orderflow/test_replay_live.py tests/market/orderflow/test_run_log.py -q`
Expected: all PASS. Then the whole suite once: `.venv/bin/python -m pytest -q -x --ignore=strader/tests 2>&1 | tail -3` — no new failures (if one fails, run that test on the commit before Task 1 to see whether it predates this work).

- [ ] **Step 2: Inbox row and spec status**

Add under the spec's title: `**Status:** landed <commit> on <date>; crons installed; backfill N days (see bead co-7kgte).`

Append to `docs/a2a/inbox.md` one WRITE row in the table's format:

```
| <YYYY-MM-DD HH:MM> CT | COO | WRITE | co-7kgte | <landing commit> | market/orderflow/postmortem.py, market/orderflow/replay_live.py, scripts/postmortem_day.py, scripts/cron/postmortem-wrapper.sh, config/postmortem.yaml, scripts/acuity_run2.py, scripts/live_parity_check.py, tests/… | DAY POST-MORTEM LANDED. 15:30 same-day and 08:27 next-morning crons (COO SCHEDULE.md); ledger data/measurement/postmortem/ (<day>.json, ledger.jsonl, legs.jsonl, recaps/); pages /var/moo/desk/desk-postmortem-<day>.html and -latest.html (Trading); backfill over N tape days, summary desk-postmortem-backfill.html. Flags for Strader on each page under "For Strader" (dense-anchor, late-confirm, silent-move, no-breakout-word, grid-density); the Friday NOTE row here with the week's counts is a follow-up bead, not in this commit. Knobs in config/postmortem.yaml are Steve's. replay_events moved out of live_parity_check.py (re-exported); acuity_run2 imports excursion_from_trades. |
```

(The Friday NOTE row from spec §3d is deliberately left to a follow-up bead so this landing is not gated on a fifth cron path; say so on the bead.)

- [ ] **Step 3: Commit and push both repos**

```bash
cd /root/projects/Strader
git add docs/a2a/inbox.md docs/superpowers/specs/2026-08-19-day-postmortem-design.md
git commit -m "postmortem: landed — inbox row, spec status [co-7kgte]"
git pull --rebase && git push
cd /root/projects/COO
git stash -q; git pull --rebase && git push; git stash pop -q
```

- [ ] **Step 4: Bead**

```bash
bd update co-7kgte --append-notes "Landed: Strader <commits>; COO SCHEDULE.md <commit>. Backfill N days ok / M skipped; legs-per-day medians at X-2/X/X+2: a/b/c; silent-near-level median d. Follow-ups: Friday NOTE row to Strader's inbox (spec §3d); knobs review after the first week of live pages."
bd close co-7kgte
```

Report to Steve in a few lines: the latest page path, the backfill medians, and that the knobs are his in `config/postmortem.yaml`.

---

## Self-review against the spec

- §2 inputs: Tasks 3 (record, replay), 11 (letter) ✔
- §3a calls: Task 5 (for/against, ±5, back-to-level, nth, confirm lag; invalidated with the setup's bias; forming counted in the census, Task 8) ✔
- §3b legs: Task 6; defaults in Task 2 ✔
- §3c recap: Task 7 + CLI wiring in Task 11 (next-morning only; statuses not-received / no-recap-section / received) ✔
- §3d flags: Task 8; the Friday NOTE row deferred explicitly in Task 14 (documented gap) ✔
- §4a ledger: Task 9 ✔ — §4b page: Task 10 (sections 1–8) ✔ — §4c logging/alerts: Task 13 ✔
- §5 schedule: Task 13 ✔ — §6 backfill: Task 12 ✔ — §7 failure handling: Tasks 3 (bar_n), 4 (truncated), 11 (no record, renderer), 13 (alerts, smoke) ✔
- §8 tests: Tasks 1–12; the morning smoke lives in the wrapper (Task 13) ✔
- §9 files: all named ✔; `.gitignore` checked in Task 10.
- Type consistency: `Knobs` fields and `knobs_to_dict` / `knobs_from_dict` used identically in Tasks 2, 5, 6, 8, 10, 12; `Segment.pos` and `Bar.i` vs list index distinguished throughout (legs use list indices internally and feeder bar numbers in rows); `measure_calls` row keys (`run`, `bar_i`, `ct`, `t1`, `type`, `setup`, `state`, `direction`, `entry`, `confidence`, `reason`, `anchor`, `fire_index`, `confirm_lag_bars`, `confirm_lag_pts`, `back_to_level_min`, `mfe{w}`, `mae{w}`, `verdict{w}`, `truncated{w}`, `session`) are consumed by `flags`, `match_recap`, `history`, `render_page`, `backfill_one` under the same names; `publish()` returns an int in every path the tests monkeypatch.
