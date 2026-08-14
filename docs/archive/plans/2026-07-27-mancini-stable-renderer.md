# Mancini Stable Renderer Implementation Plan

> **ARCHIVED 2026-08-14 — DELIVERED.** The stable renderer shipped: `runbook/mancini/payload_emitter.py` builds the Daily Payload, `run.py` pushes it to Steve's clipboard as the last step of every interpretive parse (st-5rc, st-llor), and it did exactly that this morning at 09:22 CT — 1005 bytes, 66 levels.
>
> **Its 41 checkboxes are all unticked and always were.** Nobody maintained them while the work shipped anyway, so read the checkbox state as noise, not as progress. That mismatch is why this plan sat on Steve's desk looking like 41 open tasks.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One permanent "Mancini Forecast" Pine v6 script fed by a daily text payload pushed to the Windows clipboard — replacing per-day Pine script generation (parallel-run during migration).

**Bead:** st-5rc (Stable Renderer Build) · Spec: `docs/superpowers/specs/2026-07-25-mancini-stable-renderer-design.md` (approved)

**Architecture:** Ship data, not code. A new `payload_emitter.py` renders a `ParseResult` (+ optional measured profile levels) into a compact line-based v1 payload; `run.py` gains a non-fatal chain step that pushes it to `clip.exe`; a tracked `pine/mancini_forecast.pine` parses the payload from a single `input.text_area` and owns all display/state logic (level states, zones, HUD, staleness banner, confluence ticks, notes).

**Tech Stack:** Python 3 (stdlib only, pytest), Pine Script v6, `clip.exe` via WSL interop.

---

### Task 1: Payload emitter — header + level lines

**Files:**
- Create: `runbook/mancini/payload_emitter.py`
- Test: `runbook/mancini/tests/test_payload_emitter.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for payload_emitter (st-5rc). Fixture is deliberately tiny and inline —
golden behavior is asserted line-by-line so failures name the exact line."""
from runbook.mancini.payload_emitter import build_payload
from runbook.mancini.schema import ParseResult, Level


def _result(levels):
    return ParseResult(date="2026-07-27", instrument="ES",
                       session_bias="", levels=levels, commentary=[],
                       raw_excerpt="", model="t", parsed_at="2026-07-27T13:00:00+00:00")


def test_header_and_single_levels():
    r = _result([
        Level(price=7458.0, kind="support", label="major", source_quote="7458 (major)"),
        Level(price=7453.0, kind="support", label="", source_quote="7453"),
        Level(price=7506.0, kind="resistance", label="major", source_quote="7506 (major)"),
    ])
    lines = build_payload(r).splitlines()
    assert lines[0] == "v1 2026-07-27 ES"
    assert "S 7458 . major" in lines
    assert "S 7453 . minor" in lines
    assert "R 7506 . major" in lines


def test_trigger_kind_levels_are_skipped():
    # kind='trigger' extras (e.g. 7437 shelf) are narrative anchors, not ladder
    # levels — the renderer draws the ladder; triggers stay in commentary.
    r = _result([Level(price=7437.0, kind="trigger", label="shelf", source_quote="7437")])
    assert len(build_payload(r).splitlines()) == 1  # header only
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/projects/Strader && python -m pytest runbook/mancini/tests/test_payload_emitter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'runbook.mancini.payload_emitter'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Daily payload emitter for the stable Mancini Forecast renderer. [st-5rc]

Renders a ParseResult into the v1 line-based payload the Pine renderer's
input.text_area consumes (spec: 2026-07-25-mancini-stable-renderer-design.md).

Format:
    v1 <date> <symbol>
    S|R <price> <price2|.> <major|minor> [key] [conf] ["note"]
    P poc|vah|val|lvn|hvn <price>

Only ladder levels (kind support/resistance) become S/R lines; kind='trigger'
extras remain commentary-side. Prices render trailing-zero-free (7458, 7461.5).
"""
from __future__ import annotations

from typing import Sequence

from .chart import key_prices
from .schema import Level, ParseResult

CONFLUENCE_TOLERANCE_PTS = 2.0
_PROFILE_KINDS = ("poc", "vah", "val", "lvn", "hvn")


def _fmt(price: float) -> str:
    return f"{price:g}"


def _tier(level: Level) -> str:
    return "major" if "major" in (level.label or "").lower() else "minor"


def build_payload(result: ParseResult,
                  profile_levels: Sequence[tuple[str, float]] = (),
                  *, confluence_tol: float = CONFLUENCE_TOLERANCE_PTS) -> str:
    lines = [f"v1 {result.date} {result.instrument}"]
    for lv in result.levels:
        if lv.kind == "support":
            prefix = "S"
        elif lv.kind == "resistance":
            prefix = "R"
        else:
            continue
        lines.append(f"{prefix} {_fmt(lv.price)} . {_tier(lv)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /root/projects/Strader && python -m pytest runbook/mancini/tests/test_payload_emitter.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /root/projects/Strader
git add runbook/mancini/payload_emitter.py runbook/mancini/tests/test_payload_emitter.py
git commit -m "feat(mancini): payload emitter v1 — header + ladder level lines [st-5rc]"
```

---

### Task 2: Zone pairing, key/conf flags, notes, profile lines

**Files:**
- Modify: `runbook/mancini/payload_emitter.py`
- Test: `runbook/mancini/tests/test_payload_emitter.py`

- [ ] **Step 1: Add the failing tests**

```python
from runbook.mancini.schema import Commentary, Trigger


def test_zone_pairing_by_shared_source_quote():
    # listlevels expands "7640-45" into two Levels sharing one source_quote;
    # the emitter reunites them into one zone line: near edge first.
    r = _result([
        Level(price=7640.0, kind="resistance", label="major", source_quote="7640-45 (major)"),
        Level(price=7645.0, kind="resistance", label="major", source_quote="7640-45 (major)"),
    ])
    lines = build_payload(r).splitlines()
    assert lines[1] == "R 7640 7645 major"
    assert len(lines) == 2  # one zone line, not two singles


def test_key_flag_and_note_from_commentary():
    c = Commentary(text="Bear case Monday: begins below 7434 — breakdown trade.",
                   trigger=Trigger(type="price_cross", anchor_prices=[7434.0],
                                   condition_text=""),
                   tags=[], source_quote="Bear case Monday: Begins below 7434.")
    r = ParseResult(date="2026-07-27", instrument="ES", session_bias="",
                    levels=[Level(price=7434.0, kind="support", label="major",
                                  source_quote="7434 (major)")],
                    commentary=[c], raw_excerpt="", model="t",
                    parsed_at="2026-07-27T13:00:00+00:00")
    line = build_payload(r).splitlines()[1]
    assert line.startswith("S 7434 . major key")
    assert '"Bear case Monday: begins below 7434' in line


def test_conf_flag_within_tolerance_and_profile_lines():
    r = _result([Level(price=7461.0, kind="support", label="", source_quote="7461")])
    out = build_payload(r, profile_levels=[("poc", 7461.5), ("val", 7438.0)])
    lines = out.splitlines()
    assert "S 7461 . minor conf" in lines
    assert "P poc 7461.5" in lines
    assert "P val 7438" in lines


def test_conf_flag_respects_tolerance_boundary():
    r = _result([Level(price=7461.0, kind="support", label="", source_quote="7461")])
    at_tol = build_payload(r, profile_levels=[("poc", 7463.0)])      # == 2.0 away
    beyond = build_payload(r, profile_levels=[("poc", 7463.01)])     # > 2.0 away
    assert "conf" in at_tol.splitlines()[1]
    assert "conf" not in beyond.splitlines()[1]
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd /root/projects/Strader && python -m pytest runbook/mancini/tests/test_payload_emitter.py -v`
Expected: first 2 pass, new 4 FAIL (zone renders as two lines; no key/conf/note/P support)

- [ ] **Step 3: Replace build_payload with the full implementation**

```python
def _note_for(price: float, result: ParseResult) -> str | None:
    """First sentence (<=60 chars) of the first commentary anchored on price."""
    for c in result.commentary:
        anchors = getattr(c.trigger, "anchor_prices", None) or []
        if any(abs(a - price) < 1e-9 for a in anchors):
            sentence = c.text.split(". ")[0].strip().rstrip(".")
            return (sentence[:57] + "...") if len(sentence) > 60 else sentence
    return None


def build_payload(result: ParseResult,
                  profile_levels: Sequence[tuple[str, float]] = (),
                  *, confluence_tol: float = CONFLUENCE_TOLERANCE_PTS) -> str:
    keys = key_prices(result)
    prof_prices = [p for k, p in profile_levels if k in _PROFILE_KINDS]

    # Zone pairing: ladder levels sharing (kind, source_quote) in pairs are the
    # two edges the extractor expanded from one "7640-45" token.
    groups: dict[tuple[str, str], list[Level]] = {}
    ordered: list[tuple[str, str]] = []
    for lv in result.levels:
        if lv.kind not in ("support", "resistance"):
            continue
        gk = (lv.kind, lv.source_quote or f"__solo_{_fmt(lv.price)}")
        if gk not in groups:
            groups[gk] = []
            ordered.append(gk)
        groups[gk].append(lv)

    lines = [f"v1 {result.date} {result.instrument}"]
    for gk in ordered:
        members = sorted(groups[gk], key=lambda l: l.price)
        first = members[0]
        prefix = "S" if first.kind == "support" else "R"
        if len(members) == 2:
            p1, p2 = _fmt(members[0].price), _fmt(members[1].price)
        else:
            # 1 member = single line; 3+ shared quotes are not zones — emit singly
            if len(members) > 2:
                for lv in members:
                    lines.append(_level_line(lv, "S" if lv.kind == "support" else "R",
                                             _fmt(lv.price), ".", keys, prof_prices,
                                             confluence_tol, result))
                continue
            p1, p2 = _fmt(first.price), "."
        lines.append(_level_line(first, prefix, p1, p2, keys, prof_prices,
                                 confluence_tol, result))

    for kind, price in profile_levels:
        if kind in _PROFILE_KINDS:
            lines.append(f"P {kind} {_fmt(price)}")
    return "\n".join(lines)


def _level_line(lv: Level, prefix: str, p1: str, p2: str, keys: set[float],
                prof_prices: list[float], tol: float, result: ParseResult) -> str:
    parts = [prefix, p1, p2, _tier(lv)]
    is_key = lv.price in keys
    if is_key:
        parts.append("key")
    if any(abs(lv.price - pp) <= tol for pp in prof_prices):
        parts.append("conf")
    if is_key:
        note = _note_for(lv.price, result)
        if note:
            parts.append(f'"{note}"')
    return " ".join(parts)
```

- [ ] **Step 4: Run all emitter tests**

Run: `cd /root/projects/Strader && python -m pytest runbook/mancini/tests/test_payload_emitter.py -v`
Expected: 6 passed

- [ ] **Step 5: Golden test against the real 2026-07-27 ParseResult shape**

Add to the test file (uses the live last-good parse if present; skips cleanly otherwise so CI never depends on runtime artifacts):

```python
import json, pathlib, pytest

_PARSED = pathlib.Path(__file__).resolve().parents[1] / "parsed" / "2026-07-27.json"


@pytest.mark.skipif(not _PARSED.exists(), reason="no last-good parse on this box")
def test_real_day_payload_shape_and_size():
    from runbook.mancini.schema import ParseResult, Level, Commentary, Trigger
    d = json.loads(_PARSED.read_text())
    r = ParseResult(date=d["date"], instrument=d["instrument"],
                    session_bias=d["session_bias"],
                    levels=[Level(**l) for l in d["levels"]],
                    commentary=[Commentary(text=c["text"],
                                           trigger=Trigger(**c["trigger"]),
                                           tags=c["tags"],
                                           source_quote=c["source_quote"])
                                for c in d["commentary"]],
                    raw_excerpt="", model=d["model"], parsed_at=d["parsed_at"])
    payload = build_payload(r)
    lines = payload.splitlines()
    assert lines[0] == f"v1 {d['date']} ES"
    assert 40 < len(lines) < 100
    assert len(payload.encode()) < 4096  # spec: ~2 KB for a 60-level day
```

Run: `python -m pytest runbook/mancini/tests/test_payload_emitter.py -v` — Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add runbook/mancini/payload_emitter.py runbook/mancini/tests/test_payload_emitter.py
git commit -m "feat(mancini): payload zones, key/conf flags, notes, profile lines [st-5rc]"
```

---

### Task 3: Clipboard push with injectable runner + ceiling probe payloads

**Files:**
- Modify: `runbook/mancini/payload_emitter.py`
- Test: `runbook/mancini/tests/test_payload_emitter.py`

- [ ] **Step 1: Failing tests**

```python
def test_push_clipboard_uses_injected_runner():
    sent = {}
    def fake_run(cmd, text):
        sent["cmd"], sent["text"] = cmd, text
        return 0
    from runbook.mancini.payload_emitter import push_clipboard
    rc = push_clipboard("v1 2026-07-27 ES", run=fake_run)
    assert rc == 0 and sent["cmd"] == ["clip.exe"] and sent["text"].startswith("v1 ")


def test_ceiling_probe_sizes():
    from runbook.mancini.payload_emitter import ceiling_probe
    for kb in (2, 4, 8, 16):
        p = ceiling_probe(kb)
        assert p.startswith("v1 2099-01-01 ES")
        assert abs(len(p.encode()) - kb * 1024) < 64
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest runbook/mancini/tests/test_payload_emitter.py -v` — Expected: 2 new FAIL (ImportError)

- [ ] **Step 3: Implement**

```python
import subprocess


def _default_run(cmd: list[str], text: str) -> int:
    proc = subprocess.run(cmd, input=text.encode("utf-16-le"), timeout=15)
    return proc.returncode


def push_clipboard(payload: str, *, run=_default_run) -> int:
    """Push the payload to the Windows clipboard via clip.exe (WSL interop).

    clip.exe expects UTF-16LE from a pipe; plain UTF-8 arrives mojibake'd
    (same class of bug as the WSL backup scripts, spec Known hazards)."""
    return run(["clip.exe"], payload)


def ceiling_probe(kb: int) -> str:
    """Synthetic payload of ~kb KB for the input.text_area ceiling test.

    Valid v1 format with an obviously-fake date so a leftover probe paste
    trips the STALE banner instead of masquerading as a real day."""
    lines = [f"v1 2099-01-01 ES"]
    price = 1000.0
    while len("\n".join(lines).encode()) < kb * 1024 - 24:
        lines.append(f"S {price:g} . minor")
        price += 0.25
    return "\n".join(lines)
```

- [ ] **Step 4: Run all tests** — Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add runbook/mancini/payload_emitter.py runbook/mancini/tests/test_payload_emitter.py
git commit -m "feat(mancini): clipboard push (utf-16le) + ceiling probe payloads [st-5rc]"
```

---

### Task 4: Chain step in run.py (non-fatal, parallel-run preserved)

**Files:**
- Modify: `runbook/mancini/run.py` (immediately after the 3b chart-emit block, ~line 410)

- [ ] **Step 1: Add the payload step** (same non-fatal contract as 3b; per-day pine emission above stays untouched — that IS the parallel run):

```python
    # 3b2. Stable-renderer payload → Windows clipboard (#st-5rc). Non-fatal.
    # Parallel-run: 3b keeps emitting the per-day script during migration week.
    payload_path = None
    try:
        from . import payload_emitter

        payload = payload_emitter.build_payload(result)
        payload_path = CHARTS_ROOT / f"{result.date or day}.payload.txt"
        payload_path.write_text(payload, encoding="utf-8")
        rc = payload_emitter.push_clipboard(payload)
        logger.info("stable-renderer payload: %s (%d bytes, clip rc=%d)",
                    payload_path, len(payload.encode()), rc)
    except Exception as e:  # noqa: BLE001
        logger.warning("payload emit failed (non-fatal): %s", e)
```

Note: `profile_levels` is intentionally not wired here in v1 step one — the
morning chain does not currently compute a prior-session profile inline. The
emitter accepts them; wiring the profile source is a follow-up inside the
migration week once the renderer is live (spec allows P lines to be absent).

- [ ] **Step 2: Verify by module smoke** (no live parse needed):

```bash
cd /root/projects/Strader && python - <<'EOF'
import json, sys
sys.path.insert(0, '.')
from runbook.mancini.schema import ParseResult, Level, Commentary, Trigger
from runbook.mancini import payload_emitter
d = json.load(open('runbook/mancini/parsed/2026-07-27.json'))
r = ParseResult(date=d['date'], instrument=d['instrument'], session_bias=d['session_bias'],
    levels=[Level(**l) for l in d['levels']],
    commentary=[Commentary(text=c['text'], trigger=Trigger(**c['trigger']),
                            tags=c['tags'], source_quote=c['source_quote']) for c in d['commentary']],
    raw_excerpt='', model=d['model'], parsed_at=d['parsed_at'])
print(payload_emitter.build_payload(r))
EOF
```

Expected: `v1 2026-07-27 ES` header + ~63 S/R lines, key flags on 7434/7458/7464/7506/7533/7547/7575/7311.

- [ ] **Step 3: Run the full mancini test dir** — `python -m pytest runbook/mancini/tests/ -v` — Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add runbook/mancini/run.py
git commit -m "feat(mancini): chain step — payload emit + clipboard push, parallel-run [st-5rc]"
```

---

### Task 5: The stable renderer — `pine/mancini_forecast.pine`

**Files:**
- Create: `pine/mancini_forecast.pine` (tracked — the source of record)

No automated test exists for Pine; the compile in TradingView's editor is the test (Task 7). Write the complete script:

- [ ] **Step 1: Write the file** — complete source:

```pine
//@version=6
// Mancini Forecast — STABLE renderer [st-5rc]
// Installed once; never edited daily. The day's levels arrive via the
// "Daily payload" text area (v1 format, emitted by runbook/mancini/payload_emitter.py).
// Spec: docs/superpowers/specs/2026-07-25-mancini-stable-renderer-design.md
indicator("Mancini Forecast", overlay=true, max_lines_count=500, max_labels_count=500, max_boxes_count=100)

// === Payload ===
payload = input.text_area("", "Daily payload (v1)", group="Payload",
     tooltip="Paste the morning payload here (Ctrl+A, Ctrl+V). First line: v1 <date> <symbol>")

// === Activation (carried over from per-day script) ===
useRadius        = input.bool(true,  "A. Radius from price", group="Activation")
radius           = input.float(60,   "Radius (points)", group="Activation", minval=1, maxval=500, step=5)
radiusSmooth     = input.int(5,      "Centerpoint SMA (bars)", group="Activation", minval=1, maxval=50)
useVisible       = input.bool(false, "B. Visible-range only", group="Activation")
visibleLookback  = input.int(150,    "Visible lookback (bars)", group="Activation", minval=10, maxval=2000)
useSessionFilter = input.bool(false, "C. Hide touched-today levels", group="Activation")
touchTolerance   = input.float(2,    "Touch tolerance (points)", group="Activation", minval=0, step=0.25)
alwaysShowKey    = input.bool(true,  "Always show key levels", group="Activation")
nonKeyAlpha      = input.int(50,     "Non-key transparency (%)", group="Activation", minval=0, maxval=100)

// === Display ===
showMajor   = input.bool(true,  "Show major levels", group="Display")
showMinor   = input.bool(true,  "Show minor levels", group="Display")
showLabels  = input.bool(true,  "Show price labels", group="Display")
showNotes   = input.bool(false, "Notes always visible (else tooltip)", group="Display")
extendRight = input.int(10,     "Extend right (bars)", group="Display", minval=0, maxval=500)
historyBack = input.int(300,    "History back (bars)", group="Display", minval=50, maxval=2000)
hudPos      = input.string("top_left", "HUD position", group="Display",
     options=["top_left", "top_right", "bottom_left", "bottom_right", "off"])

// === Colors ===
cSup   = input.color(#26a69a, "Support",    group="Colors")
cRes   = input.color(#ef5350, "Resistance", group="Colors")
cProf  = input.color(#b39ddb, "Profile (P) levels", group="Colors")
cStale = input.color(#d50000, "Stale banner", group="Colors")

// === Parsed payload state (filled once on first bar; inputs are constant per run) ===
var string  pDate    = ""
var string  pSymbol  = ""
var array<float>  lvPrice  = array.new<float>()
var array<float>  lvPrice2 = array.new<float>()   // na = single line
var array<bool>   lvIsSup  = array.new<bool>()
var array<bool>   lvMajor  = array.new<bool>()
var array<bool>   lvKey    = array.new<bool>()
var array<bool>   lvConf   = array.new<bool>()
var array<string> lvNote   = array.new<string>()
var array<string> profKind = array.new<string>()
var array<float>  profPrice = array.new<float>()
// state: 0 untouched · 1 tested/held · 2 broken · 3 reclaimed
var array<int>    lvState  = array.new<int>()
var array<int>    lvDefenses = array.new<int>()   // held-close count (tick marks)

_parseNote(string line) =>
    i1 = str.pos(line, "\"")
    string note = ""
    if not na(i1)
        rest = str.substring(line, i1 + 1)
        i2 = str.pos(rest, "\"")
        note := na(i2) ? rest : str.substring(rest, 0, i2)
    note

if barstate.isfirst and str.length(payload) > 0
    lines = str.split(payload, "\n")
    for li = 0 to array.size(lines) - 1
        line = str.trim(array.get(lines, li))
        if str.length(line) == 0
            continue
        toks = str.split(line, " ")
        head = array.get(toks, 0)
        if head == "v1" and array.size(toks) >= 3
            pDate   := array.get(toks, 1)
            pSymbol := array.get(toks, 2)
        else if (head == "S" or head == "R") and array.size(toks) >= 4
            price  = str.tonumber(array.get(toks, 1))
            p2tok  = array.get(toks, 2)
            price2 = p2tok == "." ? na : str.tonumber(p2tok)
            array.push(lvPrice,  price)
            array.push(lvPrice2, price2)
            array.push(lvIsSup,  head == "S")
            array.push(lvMajor,  array.get(toks, 3) == "major")
            hasKey  = false
            hasConf = false
            for ti = 4 to array.size(toks) - 1
                t = array.get(toks, ti)
                if t == "key"
                    hasKey := true
                if t == "conf"
                    hasConf := true
            array.push(lvKey,  hasKey)
            array.push(lvConf, hasConf)
            array.push(lvNote, _parseNote(line))
            array.push(lvState, 0)
            array.push(lvDefenses, 0)
        else if head == "P" and array.size(toks) >= 3
            array.push(profKind,  array.get(toks, 1))
            array.push(profPrice, str.tonumber(array.get(toks, 2)))

// === Per-bar state machine (confirmed bars only; close-based, wicks are flush noise) ===
if barstate.isconfirmed and array.size(lvPrice) > 0
    for i = 0 to array.size(lvPrice) - 1
        p    = array.get(lvPrice, i)
        p2   = array.get(lvPrice2, i)
        isSup = array.get(lvIsSup, i)
        nearEdge = na(p2) ? p : (isSup ? math.max(p, p2) : math.min(p, p2))
        farEdge  = na(p2) ? p : (isSup ? math.min(p, p2) : math.max(p, p2))
        st = array.get(lvState, i)
        touched = low <= nearEdge + touchTolerance and high >= nearEdge - touchTolerance
        heldClose   = isSup ? close > nearEdge : close < nearEdge
        brokenClose = isSup ? close < farEdge - touchTolerance : close > farEdge + touchTolerance
        if st == 0 and touched
            st := 1
        if (st == 1 or st == 0) and brokenClose
            st := 2
        if st == 2 and heldClose
            st := 3
        if (st == 1 or st == 3) and touched and heldClose
            array.set(lvDefenses, i, array.get(lvDefenses, i) + 1)
        array.set(lvState, i, st)

// === Helpers ===
centerPrice = ta.sma(close, radiusSmooth)
visHigh = ta.highest(high, visibleLookback)
visLow  = ta.lowest(low,  visibleLookback)

_shouldShow(float price, bool isKey, int st, bool isMajor) =>
    pass = true
    if not showMajor and isMajor
        pass := false
    if not showMinor and not isMajor
        pass := false
    if useRadius and math.abs(price - centerPrice) > radius
        pass := false
    if useVisible and (price > visHigh or price < visLow)
        pass := false
    if useSessionFilter and st >= 1
        pass := false
    if alwaysShowKey and isKey
        pass := true
    pass

_stateWord(int st) =>
    st == 0 ? "untouched" : st == 1 ? "held" : st == 2 ? "BROKEN" : "RECLAIMED"

// === Draw (delete-and-redraw on last bar) ===
var array<line>  _lines  = array.new<line>()
var array<label> _labels = array.new<label>()
var array<box>   _boxes  = array.new<box>()
var table hud   = na
var table stale = na

if barstate.islast
    for ln in _lines
        line.delete(ln)
    array.clear(_lines)
    for lb in _labels
        label.delete(lb)
    array.clear(_labels)
    for bx in _boxes
        box.delete(bx)
    array.clear(_boxes)

    x1 = bar_index - historyBack
    x2 = bar_index + extendRight

    if array.size(lvPrice) > 0
        for i = 0 to array.size(lvPrice) - 1
            p     = array.get(lvPrice, i)
            p2    = array.get(lvPrice2, i)
            isSup = array.get(lvIsSup, i)
            isMaj = array.get(lvMajor, i)
            isKey = array.get(lvKey, i)
            isCnf = array.get(lvConf, i)
            note  = array.get(lvNote, i)
            st    = array.get(lvState, i)
            if not _shouldShow(p, isKey, st, isMaj)
                continue
            // broken support restyles as resistance (and vice versa)
            effSup = st == 2 ? not isSup : isSup
            baseCol = effSup ? cSup : cRes
            alpha = isKey ? 0 : nonKeyAlpha
            style = st == 2 ? line.style_dashed : (isMaj ? line.style_solid : line.style_dashed)
            width = isMaj ? 2 : 1
            if isCnf
                width := width + 1
            lineCol = color.new(baseCol, alpha)
            if not na(p2)
                array.push(_boxes, box.new(x1, math.max(p, p2), x2, math.min(p, p2),
                     border_color=lineCol, border_width=1, bgcolor=color.new(baseCol, 88)))
            array.push(_lines, line.new(x1, p, x2, p, xloc.bar_index, extend.none, lineCol, style, width))
            if showLabels
                tag = (isKey ? "K " : "") + (isCnf ? "◆ " : "") + str.tostring(p, "#.##")
                     + (isSup ? " S" : " R") + (isMaj ? "*" : "")
                     + (st == 3 ? " ↺" : st == 2 ? " ✕" : "")
                     + (array.get(lvDefenses, i) > 0 ? " +" + str.tostring(array.get(lvDefenses, i)) : "")
                txt = showNotes and str.length(note) > 0 ? tag + " — " + note : tag
                // chart-left: labels sit at the left end; price axis owns the right edge
                array.push(_labels, label.new(x1, p, txt, xloc.bar_index, yloc.price,
                     color.new(color.black, 100), label.style_label_right, baseCol, size.small,
                     tooltip=str.length(note) > 0 ? note : na))

    if array.size(profPrice) > 0
        for i = 0 to array.size(profPrice) - 1
            pp = array.get(profPrice, i)
            array.push(_lines, line.new(x1, pp, x2, pp, xloc.bar_index, extend.none,
                 color.new(cProf, 30), line.style_dotted, 1))
            if showLabels
                array.push(_labels, label.new(x1, pp, str.upper(array.get(profKind, i)) + " " + str.tostring(pp, "#.##"),
                     xloc.bar_index, yloc.price, color.new(color.black, 100),
                     label.style_label_right, cProf, size.tiny))

    // === Proximity HUD ===
    if hudPos != "off"
        pos = hudPos == "top_left" ? position.top_left : hudPos == "top_right" ? position.top_right :
             hudPos == "bottom_left" ? position.bottom_left : position.bottom_right
        if na(hud)
            hud := table.new(pos, 4, 3, bgcolor=color.new(color.black, 80), border_width=1)
        float bestAbove = na
        float bestBelow = na
        int   idxAbove  = na
        int   idxBelow  = na
        if array.size(lvPrice) > 0
            for i = 0 to array.size(lvPrice) - 1
                p = array.get(lvPrice, i)
                if p > close and (na(bestAbove) or p < bestAbove)
                    bestAbove := p
                    idxAbove  := i
                if p < close and (na(bestBelow) or p > bestBelow)
                    bestBelow := p
                    idxBelow  := i
        table.cell(hud, 0, 0, "Mancini", text_color=color.white, text_size=size.small)
        table.cell(hud, 1, 0, pDate, text_color=color.gray, text_size=size.small)
        table.cell(hud, 2, 0, "", text_size=size.small)
        table.cell(hud, 3, 0, "", text_size=size.small)
        if not na(idxAbove)
            table.cell(hud, 0, 1, "▲ " + str.tostring(bestAbove, "#.##"), text_color=cRes, text_size=size.small)
            table.cell(hud, 1, 1, str.tostring(bestAbove - close, "#.#") + " pts", text_color=color.white, text_size=size.small)
            table.cell(hud, 2, 1, array.get(lvMajor, idxAbove) ? "major" : "minor", text_color=color.gray, text_size=size.small)
            table.cell(hud, 3, 1, _stateWord(array.get(lvState, idxAbove)), text_color=color.gray, text_size=size.small)
        if not na(idxBelow)
            table.cell(hud, 0, 2, "▼ " + str.tostring(bestBelow, "#.##"), text_color=cSup, text_size=size.small)
            table.cell(hud, 1, 2, str.tostring(close - bestBelow, "#.#") + " pts", text_color=color.white, text_size=size.small)
            table.cell(hud, 2, 2, array.get(lvMajor, idxBelow) ? "major" : "minor", text_color=color.gray, text_size=size.small)
            table.cell(hud, 3, 2, _stateWord(array.get(lvState, idxBelow)), text_color=color.gray, text_size=size.small)

    // === Staleness guard ===
    chartDay = str.format_time(timenow, "yyyy-MM-dd", syminfo.timezone)
    if str.length(payload) == 0
        if na(stale)
            stale := table.new(position.top_center, 1, 1, bgcolor=color.new(cStale, 10))
        table.cell(stale, 0, 0, "NO PAYLOAD — paste the morning payload into settings",
             text_color=color.white, text_size=size.large)
    else if pDate != chartDay
        if na(stale)
            stale := table.new(position.top_center, 1, 1, bgcolor=color.new(cStale, 10))
        table.cell(stale, 0, 0, "LEVELS FROM " + pDate + " — STALE", text_color=color.white, text_size=size.large)
    else if not na(stale)
        table.delete(stale)
        stale := na
```

- [ ] **Step 2: Commit**

```bash
git add pine/mancini_forecast.pine
git commit -m "feat(pine): Mancini Forecast stable renderer — payload-driven, states/zones/HUD/stale [st-5rc]"
```

Known first-compile risks (fix in the editor, then sync the file back verbatim — the tracked file is the source of record): v6 `str.pos` return-na handling, `str.trim` availability (fallback: manual trim), label `tooltip=na` typing (fallback: empty string), `table.delete` on `na`.

---

### Task 6: Daily playbook + manual verification checklist

**Files:**
- Create: `docs/playbooks/mancini-renderer-daily.md`

- [ ] **Step 1: Write the playbook**

```markdown
# Mancini Forecast — Daily Routine & Verification [st-5rc]

## Morning (4 actions, no Pine Editor)
The parse chain pushes the day's payload to the Windows clipboard automatically.
1. Double-click the **Mancini Forecast** indicator title on the /ES chart.
2. Click into the **Daily payload (v1)** field.
3. Ctrl+A, Ctrl+V.
4. OK.

## Reading the chart
- Solid = major, dashed = minor; teal = support, red = resistance.
- `K` = narrative-cited key level (always visible if the toggle is on). `◆` = profile-confluent.
- `+n` = n held closes (defenses). `✕` = broken (restyled to the other side's color, dashed). `↺` = reclaimed — the Failed Breakdown pattern rendered in place.
- HUD (default top-left): nearest level above/below, distance, tier, state.
- **Red top banner** = the payload date is not today (or no payload). Repaste before trusting anything.

## If the indicator is lost (reinstall)
Pine Editor → paste `pine/mancini_forecast.pine` from the repo → Save → Add to chart.
The repo file is the source of record; if you hotfix in the editor, sync it back.

## Manual verification protocol (run once per renderer change; live or replayed day)
- [ ] Paste today's payload → levels render; count matches the payload's S/R lines.
- [ ] Touch: watch (or bar-replay) price into a level ± tolerance → state moves untouched→held; `+n` increments on defended closes.
- [ ] Break: a CLOSE beyond a level by > tolerance → dashed restyle + `✕` (wick through must NOT trigger it).
- [ ] Reclaim: close back on the original side after a break → `↺` highlight.
- [ ] Zone: a `price2` line renders as a shaded band; touch uses near edge, break uses far edge.
- [ ] HUD shows the true nearest above/below with correct distances.
- [ ] Staleness: paste yesterday's payload deliberately → red banner; repaste today's → banner clears.
- [ ] Ceiling: paste `ceiling_probe` payloads (2/4/8/16 KB) → find the text_area limit; record it here: **limit = ___ KB**. If < 4 KB, engage the A/B split fallback (spec).
- [ ] Parity (migration week): per-day script + stable renderer on the same chart show identical level sets.
```

- [ ] **Step 2: Commit**

```bash
git add docs/playbooks/mancini-renderer-daily.md
git commit -m "docs(mancini): stable renderer daily playbook + verification protocol [st-5rc]"
```

---

### Task 7: Live validation with Steve (requires TradingView open)

**Files:** none (live session; findings recorded on the bead)

- [ ] **Step 1: Generate ceiling probes and today's payload; push today's to the clipboard**

```bash
cd /root/projects/Strader && python - <<'EOF'
import sys; sys.path.insert(0, '.')
from runbook.mancini.payload_emitter import ceiling_probe, push_clipboard
for kb in (2, 4, 8, 16):
    open(f"/tmp/probe-{kb}kb.txt", "w").write(ceiling_probe(kb))
print("probes in /tmp; now pushing today's payload")
EOF
```

- [ ] **Step 2: Steve installs the renderer** (Pine Editor → paste `pine/mancini_forecast.pine` → Save → Add to /ES chart). Expected: compiles clean; fix any v6 syntax rejections in-editor and sync the file back.
- [ ] **Step 3: Ceiling test** — paste probes ascending until truncation; record the limit in the playbook. If < 4 KB → file the A/B-split follow-up immediately.
- [ ] **Step 4: Paste today's real payload** — run the verification protocol checklist top to bottom.
- [ ] **Step 5: Parity check** — per-day `2026-07-27.pine` script on the same chart: identical level sets.
- [ ] **Step 6: Record results on st-5rc** (`bd comment`), including the measured ceiling; commit any editor-side Pine fixes.

---

### Task 8: Migration week bookkeeping

- [ ] **Step 1:** `bd comment st-5rc` — start date of the parallel-run week; per spec, per-day emission retires after one clean week (a follow-up bead retires 3b and updates the playbook).
- [ ] **Step 2:** Final commit + push; `bd close st-5rc` only after the live validation (Task 7) passes.

---

## Self-Review (completed)

- **Spec coverage:** payload v1 format (T1-2), ceiling risk + probe (T3, T7), clip.exe push (T3-4), parallel-run (T4), renderer features A-E,G + placement conventions chart-left (T5), staleness guard (T5), playbook (T6), manual protocol + parity (T6-7), migration retirement (T8). VP placement needs no task (decided as absence + P lines). Alerts/AHK/session-shading explicitly out of scope — no tasks.
- **Placeholder scan:** none; profile-source wiring explicitly deferred with rationale in T4 (spec permits absent P lines).
- **Type consistency:** `build_payload(result, profile_levels=(), *, confluence_tol)`, `push_clipboard(payload, *, run)`, `ceiling_probe(kb)` used identically across T1-T4 and T7; Pine arrays named consistently within T5.
