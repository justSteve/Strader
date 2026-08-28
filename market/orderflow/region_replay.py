"""Region-and-filter replay — the one playback engine behind every door. [co-j9t1g, co-b18wf]

Steve's request (Desk memo 20260826T013442, from him direct): *from the chart,
target a region of price action that interests you and get a full replay of
that window with the emitter scoped to a chosen subset — sweeps only,
plan-level only, any ratified slice, over any selected region.*

Desk Ruling 9 (memo 20260826T012334) makes that same replay the ACCEPTANCE
FLOOR for any change to an emission or detection path. The memo's design
constraint is that the learning view and the acceptance floor are ONE MACHINE,
because a learning view built as a separate simulator drifts and then teaches
the drift. So this module is that machine, and it has exactly three callers:

  * ``scripts/replay_emissions.py`` — the review tool (run, diff, count) and
    the process the bridge shells out to;
  * ``scripts/drill_bridge.py`` ``GET /replay`` — the FootPrint page's door,
    a shift-drag on the chart or a typed sentence;
  * ``strader/intent`` ``replay`` verb — the spoken door, the same sentence.

All three produce the same records for the same region, or this file is lying.

TWO EMISSION PATHS, ONE RECORD SHAPE. The estate emits from two places:

  tape    ``market/orderflow/tape_events.py`` over one-minute atoms — the
          PLAN-LEVEL / SUPERLATIVE / CLIMAX / ABSORPTION-CLUSTER lines the
          live scorer (``scripts/live_effort_effect.py``) writes. Re-emitted
          here exactly as ``LiveScorer._close_minute`` does it: bucket, grade
          against the day so far, hand the pair to the detector.
  engine  ``market/orderflow/parity.py`` ``StackDriver`` over volume bars —
          sweeps, imbalance stacks, divergences, setup recognitions. Driven
          the LIVE way (``live_drive`` + ``LiveAnchors``: closed bars only,
          range edges that develop with the cash session), not the drill
          page's batch way, because the question the surface answers is
          "what would the instrument have said" and live is the instrument.
          The drill page's own per-bar ``ev`` uses the batch rule with the
          finished day's extremes as anchors from bar 0; those two agree on
          every bar except where an extreme had not printed yet. This module
          takes the live side of that known divergence, on purpose.

THE REGION NARROWS WHAT IS REPORTED, NEVER WHAT THE DETECTORS SEE. Session
extrema, cooldowns, cluster runs and range edges are all path-dependent, so a
detector fed a window would fire differently inside it. Every path runs the
whole day; the region and filter are applied to the result. That is why a
region replay is cheap to cache per day and why a windowed run is always a
strict subset of the full-day run (pinned by test).

DETERMINISM. Nothing here reads a wall clock. Same tape, same knobs, same
code: byte-identical records. Two runs over one region with unchanged code
are identical, or the diff this tool produces means nothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as _date, datetime, time as _time, timedelta
from typing import Iterable

from market.orderflow.anchored_profile import RTH_OPEN_CT as _RTH_OPEN_T, anchor_utc
from market.orderflow.anchors import LiveAnchors, mancini_kinds_for, mancini_levels_for
from market.orderflow.bars import build_bars
from market.orderflow.moves import grade_atoms_developing, one_minute_atoms
from market.orderflow.parity import StackDriver, live_drive
from market.orderflow.replay import has_es_day, read_corpus_day
from market.orderflow.tape_events import (
    KIND_ABSORPTION, KIND_CLIMAX, KIND_PLAN_LEVEL, KIND_SUPERLATIVE, EventKnobs,
    SIG_ALERT, SIG_NOTE, TapeEventDetector, load_knobs,
)
from market.orderflow.tpo import RTH_END
from market.signals.orderflow_config import VOLUME_BAR_N

log = logging.getLogger("region_replay")

# The cash session, from the two places the estate already declares it rather
# than from a third constant here.
RTH_WINDOW = (_RTH_OPEN_T, RTH_END)

PATH_TAPE = "tape"
PATH_ENGINE = "engine"
PATHS = (PATH_TAPE, PATH_ENGINE)

# ── the vocabulary ─────────────────────────────────────────────────────────
# Every kind either path can emit, with the path that emits it. Validating a
# filter against a real list rather than accepting any string is Ruling 9's
# own discipline: a filter that silently matches nothing looks exactly like a
# region with no events in it.
#
# NOT YET LEXICON IDS. Steve's replay intent asks that emission types carry
# their identity from the schema so filtering is a lexicon lookup rather than
# a string match. tape_events is not migrated to the emission schema (that
# rides st-cua1 / st-iq9g) and the engine's ``type`` strings predate it. When
# the migration lands this table is replaced by a read of
# ``emission.templates[].id`` and this comment goes with it.
KIND_SWEEP = "SweepPrint"
KIND_STACK = "ImbalanceStack"
KIND_SETUP = "SetupRecognition"
KIND_DIVERGENCE = "DeltaDivergence"
KIND_ABSORPTION_READ = "AbsorptionRead"
KIND_LEVEL = "Level"

PATH_OF: dict[str, str] = {
    KIND_PLAN_LEVEL: PATH_TAPE, KIND_SUPERLATIVE: PATH_TAPE,
    KIND_CLIMAX: PATH_TAPE, KIND_ABSORPTION: PATH_TAPE,
    KIND_SWEEP: PATH_ENGINE, KIND_STACK: PATH_ENGINE, KIND_SETUP: PATH_ENGINE,
    KIND_DIVERGENCE: PATH_ENGINE, KIND_ABSORPTION_READ: PATH_ENGINE,
    KIND_LEVEL: PATH_ENGINE,
}
KNOWN_KINDS: tuple[str, ...] = tuple(PATH_OF)
KNOWN_SIGS = (SIG_ALERT, SIG_NOTE)

# The words Steve says → the kinds they name. One word may name kinds on both
# paths ("absorption"). The spoken door and the page's chips both read this,
# so adding a word here adds it everywhere.
KIND_WORDS: dict[str, tuple[str, ...]] = {
    "plan-level": (KIND_PLAN_LEVEL,), "plan level": (KIND_PLAN_LEVEL,),
    "plan levels": (KIND_PLAN_LEVEL,), "levels": (KIND_PLAN_LEVEL,),
    "level": (KIND_PLAN_LEVEL,),
    "sweeps": (KIND_SWEEP,), "sweep": (KIND_SWEEP,),
    "stacks": (KIND_STACK,), "stack": (KIND_STACK,),
    "imbalance": (KIND_STACK,), "imbalances": (KIND_STACK,),
    "setups": (KIND_SETUP,), "setup": (KIND_SETUP,),
    "recognitions": (KIND_SETUP,), "recognition": (KIND_SETUP,),
    "divergence": (KIND_DIVERGENCE,), "divergences": (KIND_DIVERGENCE,),
    "absorption": (KIND_ABSORPTION, KIND_ABSORPTION_READ),
    "climax": (KIND_CLIMAX,), "climaxes": (KIND_CLIMAX,),
    "superlative": (KIND_SUPERLATIVE,), "superlatives": (KIND_SUPERLATIVE,),
    "records": (KIND_SUPERLATIVE,), "extremes": (KIND_SUPERLATIVE,),
    "profile": (KIND_LEVEL,), "profile levels": (KIND_LEVEL,),
}
# What a kind is called back to Steve. Short, the way the page's chips say it.
KIND_LABEL: dict[str, str] = {
    KIND_PLAN_LEVEL: "plan-level", KIND_SUPERLATIVE: "superlatives",
    KIND_CLIMAX: "climax", KIND_ABSORPTION: "absorption clusters",
    KIND_SWEEP: "sweeps", KIND_STACK: "stacks", KIND_SETUP: "setups",
    KIND_DIVERGENCE: "divergences", KIND_ABSORPTION_READ: "absorption reads",
    KIND_LEVEL: "profile levels",
}


def vocabulary() -> dict:
    """The filter vocabulary as one JSON-able object: the page builds its chips
    from this and the grammar reads its words from it, so neither holds a copy."""
    return {
        "kinds": [{"id": k, "path": PATH_OF[k], "label": KIND_LABEL[k]} for k in KNOWN_KINDS],
        "words": {w: list(ks) for w, ks in KIND_WORDS.items()},
        "sigs": list(KNOWN_SIGS),
        "paths": list(PATHS),
    }


# ── region and filter ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Region:
    """What slice of tape to report. A day range, optionally narrowed to an
    intra-day window (CT) and a price band."""

    start: _date
    end: _date
    between: tuple[_time, _time] | None = None
    price_band: tuple[float, float] | None = None

    def days(self):
        d = self.start
        while d <= self.end:
            yield d
            d += timedelta(days=1)

    def covers(self, ts: datetime, low: float | None, high: float | None) -> bool:
        """Does an emission at ``ts`` from a bar spanning ``low..high`` fall in
        the region? A bar whose traded range overlapped the band did its
        business there — the close alone would miss a bar that touched the
        band and left. An emission with no price span (an end-of-stream flush)
        is placed by time only."""
        if self.between is not None:
            lo, hi = self.between
            if not (lo <= ts.time() <= hi):
                return False
        if self.price_band is not None and low is not None and high is not None:
            lo, hi = self.price_band
            if high < lo or low > hi:
                return False
        return True

    def covers_atom(self, atom) -> bool:
        return self.covers(atom.ts, atom.low, atom.high)

    def describe(self) -> str:
        days = self.start.isoformat() if self.start == self.end else f"{self.start} to {self.end}"
        out = days
        if self.between is not None:
            out += f" {self.between[0]:%H:%M}-{self.between[1]:%H:%M} CT"
        if self.price_band is not None:
            out += f", {self.price_band[0]:g}-{self.price_band[1]:g}"
        return out


@dataclass(frozen=True)
class Filter:
    """Which emissions to keep. Empty means everything of that axis."""

    kinds: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    sigs: frozenset[str] = frozenset()

    def keeps(self, rec: dict) -> bool:
        if self.kinds and rec["kind"] not in self.kinds:
            return False
        if self.subtypes and rec["subtype"] not in self.subtypes:
            return False
        # An engine record carries no sig; a sig filter is a question about
        # the tape path and excludes what cannot answer it.
        if self.sigs and rec.get("sig") not in self.sigs:
            return False
        return True

    def paths(self) -> tuple[str, ...]:
        """Which emission paths this filter can keep anything from. A
        sweeps-only replay never needs the tape path run at all."""
        if not self.kinds:
            return PATHS if not self.sigs else (PATH_TAPE,)
        return tuple(p for p in PATHS if any(PATH_OF.get(k) == p for k in self.kinds))

    def describe(self) -> str:
        if not (self.kinds or self.subtypes or self.sigs):
            return "everything"
        parts = []
        if self.kinds:
            parts.append(" and ".join(KIND_LABEL.get(k, k) for k in sorted(self.kinds)))
        if self.subtypes:
            parts.append("subtype " + "/".join(sorted(self.subtypes)))
        if self.sigs:
            parts.append("sig " + "/".join(sorted(self.sigs)))
        return ", ".join(parts) + " only"


def resolve_kinds(words: Iterable[str]) -> tuple[frozenset[str], list[str]]:
    """Spoken or typed kind words → kinds, plus the words nothing matched.
    Accepts canonical ids too, so the page can send what the vocabulary gave it."""
    kinds: set[str] = set()
    unknown: list[str] = []
    for w in words:
        key = w.strip().lower()
        if not key:
            continue
        if w.strip() in PATH_OF:
            kinds.add(w.strip())
        elif key in KIND_WORDS:
            kinds.update(KIND_WORDS[key])
        else:
            unknown.append(w.strip())
    return frozenset(kinds), unknown


# ── the two paths ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Emission:
    """One emitted record with the span the region test needs. ``low``/``high``
    are the emitting bar's traded range; None when the emission belongs to no
    bar (end-of-stream)."""

    ts: datetime
    low: float | None
    high: float | None
    record: dict = field(compare=False)


def _tape_record(day: _date, ev) -> dict:
    """``TapeEvent.line()`` is the canonical human rendering and is carried
    verbatim so a diff shows exactly what the log would have shown. The parsed
    fields sit beside it so a diff can also say WHICH field moved."""
    return {
        "day": day.isoformat(),
        "ts": ev.ts.isoformat(),
        "path": PATH_TAPE,
        "kind": ev.kind,
        "subtype": ev.subtype,
        "sig": ev.sig,
        "fields": {k: v for k, v in ev.fields},
        "line": ev.line(),
    }


def tape_path(day: _date, knobs: EventKnobs, trades=None) -> list[Emission]:
    """Re-emit one archived day through the tape-event detector.

    The pipeline is the live one, not a reimplementation of it: bucket trades
    into closed minutes, grade each causally against the day SO FAR, hand the
    (atom, dev) pair to the detector. If this ever diverges from
    ``LiveScorer._close_minute`` the tool is lying, which is why it borrows the
    same three functions rather than inlining their behaviour.
    """
    trades = read_corpus_day(day) if trades is None else trades
    if not trades:
        return []
    detector = TapeEventDetector(levels=mancini_levels_for(day),
                                 kinds=mancini_kinds_for(day), knobs=knobs)
    out: list[Emission] = []
    atoms: list = []
    buf: list = []
    minute_key = None

    def close_minute():
        nonlocal buf
        if not buf:
            return
        atom = one_minute_atoms(buf)[0]
        buf = []
        atoms.append(atom)
        # Graded against everything up to and including this atom, never past
        # it. The detector must see exactly what it saw live or the diff is
        # against a fiction.
        dev = grade_atoms_developing(atoms)[-1]
        for ev in detector.on_atom(atom, dev):
            out.append(Emission(atom.ts, atom.low, atom.high, _tape_record(day, ev)))

    for t in trades:
        key = t.ts.replace(second=0, microsecond=0)
        if minute_key is not None and key != minute_key:
            close_minute()
        minute_key = key
        buf.append(t)
    close_minute()
    return out


# Engine event fields that are bookkeeping rather than content. Everything
# else on the event is carried as a field so the diff can name what moved.
_ENGINE_META = ("type", "timestamp", "source", "reason", "bar_i")
# Which of an engine event's fields say WHAT it is about, for the subtype slot
# of the record: a sweep has a direction, a divergence a kind, a recognition a
# setup and a state.
_ENGINE_SUBTYPE = {
    KIND_SWEEP: ("direction",), KIND_STACK: ("direction",),
    KIND_DIVERGENCE: ("kind",), KIND_SETUP: ("setup", "state"),
    KIND_ABSORPTION_READ: ("side", "direction"), KIND_LEVEL: ("kind", "label"),
}


def _engine_record(day: _date, ts: datetime, e: dict, bar_i: int | None) -> dict:
    kind = str(e.get("type") or "?")
    subtype = " ".join(str(e[k]) for k in _ENGINE_SUBTYPE.get(kind, ()) if e.get(k) is not None)
    fields = {k: v for k, v in e.items() if k not in _ENGINE_META}
    reason = str(e.get("reason") or "")
    line = (f"{ts:%H:%M:%S} CT  ENGINE {kind} {subtype}  {reason}").rstrip()
    return {
        "day": day.isoformat(),
        "ts": ts.isoformat(),
        "path": PATH_ENGINE,
        "kind": kind,
        "subtype": subtype,
        "sig": None,
        "fields": fields,
        "line": line,
        "bar_i": bar_i,
    }


def _bars_with_trades(trades: list, bar_n: int):
    """Closed bars paired with the trade slice that built each — the same
    slice, by the same straddle convention, that ``full_stack_events`` cuts.
    Yields ``(bar, slice)``; the trailing under-N tail is returned separately
    by the caller reading ``idx`` afterwards, so the live rule (closed bars
    only, tail to ``finish``) holds."""
    idx = 0
    for bar in build_bars(iter(trades), n=bar_n, include_partial=False):
        vol = 0
        start = idx
        while idx < len(trades) and vol < bar.volume:
            vol += trades[idx].size
            idx += 1
        yield bar, trades[start:idx]
    # the caller needs where the closed bars ended
    yield None, trades[idx:]


def engine_path(day: _date, bar_n: int = VOLUME_BAR_N, trades=None) -> list[Emission]:
    """Re-emit one archived day through the full stack the LIVE way.

    ``live_drive`` + ``LiveAnchors`` is the loop the feeder runs: the bar
    extends the developing cash-session range, then is judged against it;
    closed bars only, the tail to ``finish``. Mancini levels are today's parse
    of that day, which is what live held (they come from the pre-open parse).
    """
    trades = read_corpus_day(day) if trades is None else trades
    if not trades:
        return []
    try:
        mancini = mancini_levels_for(day)
        kinds = mancini_kinds_for(day)
    except Exception as e:  # noqa: BLE001 — no anchors must not stop the replay
        log.warning("no Mancini levels for %s (%s) — range edges only", day, e)
        mancini, kinds = [], {}
    live_anchors = LiveAnchors(mancini, session_open=anchor_utc(day, _RTH_OPEN_T), kinds=kinds)
    driver = StackDriver(anchors=live_anchors.anchors, mancini_prices=mancini)
    live_anchors.attach(driver.recognizer)

    out: list[Emission] = []
    tail: list = []
    pairs = []
    for bar, slice_ in _bars_with_trades(trades, bar_n):
        if bar is None:
            tail = slice_
        else:
            pairs.append((bar, slice_))
    for bar_i, bar, _slice, events in live_drive(iter(pairs), driver, live_anchors):
        ts = bar.end_ts
        for e in events:
            out.append(Emission(ts, bar.low, bar.high, _engine_record(day, ts, e, bar_i)))
    if tail or pairs:
        end_ts = tail[-1].ts if tail else pairs[-1][0].end_ts
        for e in driver.finish(tail):
            out.append(Emission(end_ts, None, None, _engine_record(day, end_ts, e, None)))
    return out


# ── the day cache ──────────────────────────────────────────────────────────
# A region narrows what is REPORTED, so one full-day run serves every region
# and filter asked of that day in this process. Keyed on everything the
# result depends on: the day, the knobs (a frozen dataclass, hashable) and the
# bar size. Code is not in the key — a process that changed code is a new
# process. Bounded so a long-lived bridge does not hold every day it ever saw.
_CACHE: dict[tuple, list[Emission]] = {}
_CACHE_MAX = 12


def _cached(key: tuple, build) -> list[Emission]:
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    val = build()
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = val
    return val


def clear_cache() -> None:
    _CACHE.clear()


def emit_day(day: _date, knobs: EventKnobs | None = None, *, paths: Iterable[str] = PATHS,
             bar_n: int = VOLUME_BAR_N) -> list[Emission]:
    """Every emission of ``day`` from the requested paths, in time order.
    Runs each path once per process and caches it; a second region on the
    same day costs nothing."""
    knobs = knobs or load_knobs()
    want = tuple(p for p in PATHS if p in set(paths))
    if not want:
        return []
    trades = None
    out: list[Emission] = []
    if PATH_TAPE in want:
        key = (day, PATH_TAPE, knobs)
        if key not in _CACHE:
            trades = trades if trades is not None else read_corpus_day(day)
        out += _cached(key, lambda: tape_path(day, knobs, trades))
    if PATH_ENGINE in want:
        key = (day, PATH_ENGINE, bar_n)
        if key not in _CACHE:
            trades = trades if trades is not None else read_corpus_day(day)
        out += _cached(key, lambda: engine_path(day, bar_n, trades))
    # Time order across both paths; a tie keeps the tape path first because
    # its timestamp is the minute close and the engine's is the bar close,
    # which is the order the live panes show them in.
    out.sort(key=lambda em: (em.ts, 0 if em.record["path"] == PATH_TAPE else 1))
    return out


def select(emissions: Iterable[Emission], region: Region, filt: Filter) -> list[dict]:
    """Apply the region and the filter to a day's emissions. A view: the
    records come back unchanged, or the learning surface would teach
    something the instrument never said."""
    return [em.record for em in emissions
            if region.covers(em.ts, em.low, em.high) and filt.keeps(em.record)]


def replay_day(day: _date, region: Region, filt: Filter, knobs: EventKnobs | None = None,
               *, bar_n: int = VOLUME_BAR_N, paths: Iterable[str] | None = None) -> list[dict]:
    """Re-emit one archived day and report the region. Records in emission
    order. ``paths`` restricts which emission paths run on top of what the
    filter's kinds imply (a live-log audit wants the tape path alone)."""
    want = filt.paths() if paths is None else tuple(p for p in filt.paths() if p in set(paths))
    return select(emit_day(day, knobs, paths=want, bar_n=bar_n), region, filt)


def replay(region: Region, filt: Filter, knobs: EventKnobs | None = None,
           *, bar_n: int = VOLUME_BAR_N, paths: Iterable[str] | None = None) -> list[dict]:
    records: list[dict] = []
    missing: list[str] = []
    for day in region.days():
        if not has_es_day(day):
            missing.append(day.isoformat())
            continue
        day_records = replay_day(day, region, filt, knobs, bar_n=bar_n, paths=paths)
        records.extend(day_records)
        log.info("%s  %d events", day, len(day_records))
    if missing:
        # Never silent. A region whose archive has holes produces a smaller
        # count that looks like a real result, and Ruling 9 turns on counts.
        log.warning("%d day(s) not in the corpus and NOT replayed: %s",
                    len(missing), ", ".join(missing))
    return records


# ── diff ───────────────────────────────────────────────────────────────────

# Fields that say WHICH thing an event is about, as opposed to what was
# measured about it. The distinction is the whole of the diff's usefulness:
# a subject distinguishes two events, a measurement moving is one event
# changing. Get it wrong in one direction and a real change hides; wrong in
# the other and every changed number reads as a deletion plus an insertion.
#
# `level` earns its place by measurement, not by guess: on 2026-08-25 09:30 a
# single bar fired PLAN-LEVEL TOUCH against BOTH 7665 (support) and 7667
# (resistance). Keyed on (ts, kind, subtype) alone those two collapse into
# one, and a diff would have silently dropped half of every such minute.
# The engine fields are the same idea on that path: the price a sweep started
# at, the anchor a recognition formed on, the extreme a divergence measured.
SUBJECT_FIELDS = ("level", "start_price", "anchor_price", "price_extreme", "price", "prices")


def _hashable(v):
    return tuple(v) if isinstance(v, list) else v


def _key(rec: dict) -> tuple:
    """Identity of an event across two runs: when, what kind, and about what.

    Excludes the rendered line and every measured value, so a changed number
    reads as a modification rather than as one deletion plus one insertion.
    Includes the subject fields, because one minute can carry several events
    of one kind about different things.
    """
    fields = rec.get("fields") or {}
    return (rec["ts"], rec["kind"], rec["subtype"],
            tuple(_hashable(fields.get(f)) for f in SUBJECT_FIELDS))


def diff(before: list[dict], after: list[dict]) -> dict:
    b = {_key(r): r for r in before}
    a = {_key(r): r for r in after}
    added = [a[k] for k in a.keys() - b.keys()]
    removed = [b[k] for k in b.keys() - a.keys()]
    changed = [(b[k], a[k]) for k in b.keys() & a.keys()
               if b[k]["line"] != a[k]["line"]]
    for group in (added, removed):
        group.sort(key=lambda r: r["ts"])
    changed.sort(key=lambda p: p[0]["ts"])
    return {
        "before_count": len(before), "after_count": len(after),
        "added": added, "removed": removed, "changed": changed,
        "identical": not (added or removed or changed),
    }


def render_diff(d: dict) -> str:
    lines = [
        f"before: {d['before_count']} events",
        f"after:  {d['after_count']} events",
        "",
    ]
    if d["identical"]:
        lines.append("BYTE-IDENTICAL — every event matched, none added or removed.")
        lines.append("A silent-intent change is proven silent over this region.")
        return "\n".join(lines)

    lines.append(f"NOT identical: +{len(d['added'])} / -{len(d['removed'])} / "
                 f"~{len(d['changed'])} changed")
    lines.append("")
    for r in d["removed"]:
        lines.append(f"  - {r['day']}  {r['line']}")
    for r in d["added"]:
        lines.append(f"  + {r['day']}  {r['line']}")
    for b, a in d["changed"]:
        lines.append(f"  ~ {b['day']}  {b['line']}")
        lines.append(f"    {' ' * len(b['day'])}  {a['line']}")
    return "\n".join(lines)


__all__ = [
    "Region", "Filter", "Emission", "RTH_WINDOW", "PATHS", "PATH_TAPE", "PATH_ENGINE",
    "KNOWN_KINDS", "KNOWN_SIGS", "KIND_WORDS", "KIND_LABEL", "PATH_OF", "SUBJECT_FIELDS",
    "vocabulary", "resolve_kinds", "tape_path", "engine_path", "emit_day", "select",
    "replay_day", "replay", "diff", "render_diff", "clear_cache",
]
