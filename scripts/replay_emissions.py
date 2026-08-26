#!/usr/bin/env python3
"""Re-emit archived tape through current code, and diff two such runs.

Desk Ruling 9 (memo 20260826T012334, from Steve direct): *the replayability of
verbatim current code against the historical datastore is a core property of
this estate; leverage it always when possible, and ensure updates do not
degrade it.* Every change touching an emission or detection path ships with a
re-emission diff over archived tape as its review artifact — a silent-intent
change proves byte-identical, a behavior change presents the diff as the
evidence, counted.

That capability existed only as artisanal practice: whoever ran the two-tier
cutover proof, the sweep census, the rolling-window evidence gate each built it
by hand for one occasion. This is co-b18wf, the runner, and its first arm is
the plan-level EVENT path because that is the one with a bead waiting on it
(st-cua1 cannot land its fourth kind without a diff to show).

WHY THIS PATH FIRST. ``scripts/regen_parity_snapshot.py`` already replays the
orderflow engine — sweeps, divergence, absorption — against a committed tick
slice, and it works; it is the proven, scoped version of this idea. Nothing
replayed ``market/orderflow/tape_events.py`` at all. The gap was never the
concept, it was coverage.

REGION AND FILTER ARE HERE FROM DAY ONE, NOT LATER. Steve's region-targeted
replay intent (memo 20260826T013442) asks for the same machine with two knobs
in front: pick a region of tape, scope the emitter to a chosen subset, and
watch what the instrument would have said. Retrofitting scoping onto a
whole-session runner is the expensive version, so ``--from/--to``,
``--between``, ``--kind``, ``--subtype`` and ``--sig`` exist now even though
today's only caller is review tooling. The learning view and the acceptance
floor are deliberately the same code — that is what stops the learning view
ever lying about what live code would do.

DETERMINISM. Nothing here reads a wall clock. Every decision keys off
``Trade.ts``, the same property ``LiveScorer`` documents and the parity harness
depends on. Two runs over one region with unchanged code are byte-identical, or
this tool is broken and the diff it produces means nothing.

WHAT IS PROVEN. Read this before quoting a number from it.

*Proven:* two runs of this tool over one region are byte-identical with
unchanged code, and a code change shows up as a counted diff. That is exactly
what Ruling 9 asks for as a review artifact, and it is what st-cua1 needs to
land its fourth plan-level kind with evidence rather than argument.

*Also proven, 2026-08-26 (st-v3wj):* a replay reproduces what the live emitter
actually said. 2026-08-25 is the one day with both a full live log and an
archive, and it reproduces exactly — 102 EVENT lines against the 102 in
``/var/moo/logs/effort-effect/2026-08-25.log``, compared line by line, all 102
byte-identical, PLAN-LEVEL 37/28/10 = 75 either way::

    scripts/replay_emissions.py run --from 2026-08-25 --to 2026-08-25 -o r.jsonl
    # then compare each row's "line" field against the log's EVENT lines

THE EARLIER MISMATCH WAS A BAD BASELINE, not a defect in this tool. This
docstring used to record the live side as 74 events (PLAN-LEVEL 25/19/8 = 52)
and name the anchor set as the suspect. That 74 was a PARTIAL-DAY count,
copied from ``docs/reviews/2026-08-25-emission-vocabulary-review.md``, whose
census was taken mid-session: the log stands at exactly 74 / 25/19/8 between
12:28 and 13:15 CT on 08-25 and grows to 102 / 37/28/10 by 22:52. Nothing was
ever wrong with the anchor set — the live scorer loaded 68 anchors at its
10:28 restart, the same 68 ``mancini_levels_for`` resolves today.

The near miss worth remembering: ``scripts/live_footprint_feed.py`` genuinely
DID run 08-25 with zero anchors (st-kxnv, a real and separate bug), and its
``live-parity`` run row records ``mancini: []``. That is a different process
from this one. ``live_effort_effect.py:261`` loads anchors on its own, and the
EVENT tier is its output, not the feeder's. A zero in the feeder's run row
says nothing about the scorer's log.

So: this tool may be used both to compare a change against itself and to audit
a historical log.

USE — prove a change silent::

    scripts/replay_emissions.py run --from 2026-08-01 --to 2026-08-25 -o before.jsonl
    # ... make the change ...
    scripts/replay_emissions.py run --from 2026-08-01 --to 2026-08-25 -o after.jsonl
    scripts/replay_emissions.py diff before.jsonl after.jsonl

USE — scope to what you are actually changing::

    scripts/replay_emissions.py run --from 2026-08-25 --to 2026-08-25 \\
        --kind PLAN-LEVEL --between 13:30-15:00 -o pm.jsonl

Bead: co-b18wf. Downstream surface: co-j9t1g.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date as _date, datetime, time as _time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market.orderflow.anchors import mancini_kinds_for, mancini_levels_for  # noqa: E402
from market.orderflow.moves import grade_atoms_developing, one_minute_atoms  # noqa: E402
from market.orderflow.replay import has_es_day, read_corpus_day  # noqa: E402
from market.orderflow.tape_events import (  # noqa: E402
    KIND_ABSORPTION, KIND_CLIMAX, KIND_PLAN_LEVEL, KIND_SUPERLATIVE,
    RTH_OPEN_CT, SIG_ALERT, SIG_NOTE, TapeEventDetector, knobs_to_dict,
    load_knobs,
)
from market.orderflow.tpo import RTH_END  # noqa: E402

# The cash session, from the two places the estate already declares it rather
# than from a third constant here. RTH matters enough to have a flag because of
# the trap in the next comment down.
RTH_WINDOW = (_time(*RTH_OPEN_CT), RTH_END)

log = logging.getLogger("replay_emissions")

# The declared emission vocabulary of this path. Validating --kind against a
# real list rather than accepting any string is Ruling 9's own discipline: a
# filter that silently matches nothing looks exactly like a region with no
# events in it.
#
# NOT YET LEXICON IDS. Steve's replay intent asks that emission types carry
# their identity from the schema so filtering is a lexicon lookup rather than a
# string match (Ruling 1 item 5, third argument). tape_events is not migrated
# to the emission schema — that migration rides st-cua1 and st-iq9g. When it
# lands, this tuple is replaced by a read of emission.templates[].id and this
# comment goes with it. Until then the constants module is the single source
# and importing them beats retyping them.
KNOWN_KINDS = (KIND_SUPERLATIVE, KIND_ABSORPTION, KIND_CLIMAX, KIND_PLAN_LEVEL)
KNOWN_SIGS = (SIG_ALERT, SIG_NOTE)


@dataclass(frozen=True)
class Region:
    """What slice of tape to re-emit. A day range, optionally narrowed to an
    intra-day window and a price band."""

    start: _date
    end: _date
    between: tuple[_time, _time] | None = None
    price_band: tuple[float, float] | None = None

    def days(self):
        d = self.start
        while d <= self.end:
            yield d
            d += timedelta(days=1)

    def covers_atom(self, atom) -> bool:
        if self.between is not None:
            lo, hi = self.between
            if not (lo <= atom.ts.time() <= hi):
                return False
        if self.price_band is not None:
            lo, hi = self.price_band
            # The atom's traded range overlapping the band, not just its close:
            # a bar that touched the band did its business there.
            if atom.high < lo or atom.low > hi:
                return False
        return True


@dataclass(frozen=True)
class Filter:
    """Which emissions to keep. Empty means everything of that axis."""

    kinds: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    sigs: frozenset[str] = frozenset()

    def keeps(self, ev) -> bool:
        if self.kinds and ev.kind not in self.kinds:
            return False
        if self.subtypes and ev.subtype not in self.subtypes:
            return False
        if self.sigs and ev.sig not in self.sigs:
            return False
        return True


def replay_day(day: _date, region: Region, filt: Filter, knobs) -> list[dict]:
    """Re-emit one archived day. Returns event records, in emission order.

    The pipeline is the live one, not a reimplementation of it: bucket trades
    into closed minutes, grade each causally against the day SO FAR, hand the
    (atom, dev) pair to the detector. If this ever diverges from
    ``LiveScorer._close_minute`` the tool is lying, which is why it borrows the
    same three functions rather than inlining their behaviour.
    """
    trades = read_corpus_day(day)
    if not trades:
        return []

    levels = mancini_levels_for(day)
    kinds = mancini_kinds_for(day)
    detector = TapeEventDetector(levels=levels, kinds=kinds, knobs=knobs)

    out: list[dict] = []
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
        events = detector.on_atom(atom, dev)
        # The region narrows what we REPORT, never what the detector SEES:
        # session extrema, cooldowns and cluster runs are all path-dependent,
        # so feeding it a window would change what fires inside the window.
        if not region.covers_atom(atom):
            return
        for ev in events:
            if filt.keeps(ev):
                out.append(_record(day, ev))

    for t in trades:
        key = t.ts.replace(second=0, microsecond=0)
        if minute_key is not None and key != minute_key:
            close_minute()
        minute_key = key
        buf.append(t)
    close_minute()
    return out


def _record(day: _date, ev) -> dict:
    """One event as a stable, diffable record.

    ``TapeEvent.line()`` is the canonical human rendering and is carried
    verbatim so a diff shows exactly what the log would have shown. The parsed
    fields sit beside it so a diff can also say WHICH field moved, and the day
    is explicit because ``line()`` carries only the time.
    """
    return {
        "day": day.isoformat(),
        "ts": ev.ts.isoformat(),
        "kind": ev.kind,
        "subtype": ev.subtype,
        "sig": ev.sig,
        "fields": {k: v for k, v in ev.fields},
        "line": ev.line(),
    }


def replay(region: Region, filt: Filter, knobs) -> list[dict]:
    records: list[dict] = []
    missing: list[str] = []
    for day in region.days():
        if not has_es_day(day):
            missing.append(day.isoformat())
            continue
        day_records = replay_day(day, region, filt, knobs)
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
# one, and a diff would have silently dropped half of every such minute. Found
# by test_a_window_narrows_what_is_reported_not_what_fires, which compared a
# windowed run against the full day and found "the same event" rendering two
# different ways.
SUBJECT_FIELDS = ("level",)


def _key(rec: dict) -> tuple:
    """Identity of an event across two runs: when, what kind, and about what.

    Excludes the rendered line and every measured value, so a changed number
    reads as a modification rather than as one deletion plus one insertion.
    Includes the subject fields, because one minute can carry several events
    of one kind about different things.
    """
    fields = rec.get("fields") or {}
    return (rec["ts"], rec["kind"], rec["subtype"],
            tuple(fields.get(f) for f in SUBJECT_FIELDS))


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


# ── cli ────────────────────────────────────────────────────────────────────

def _parse_day(s: str) -> _date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_between(s: str) -> tuple[_time, _time]:
    try:
        lo, hi = s.split("-")
        return (datetime.strptime(lo.strip(), "%H:%M").time(),
                datetime.strptime(hi.strip(), "%H:%M").time())
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--between wants HH:MM-HH:MM in CT, got {s!r}") from None


def _parse_band(s: str) -> tuple[float, float]:
    try:
        lo, hi = (float(x) for x in s.split("-"))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--price wants LOW-HIGH, got {s!r}") from None
    if lo > hi:
        lo, hi = hi, lo
    return (lo, hi)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="re-emit a region of archived tape")
    r.add_argument("--from", dest="start", type=_parse_day, required=True,
                   metavar="YYYY-MM-DD")
    r.add_argument("--to", dest="end", type=_parse_day, metavar="YYYY-MM-DD",
                   help="defaults to --from, i.e. a single day")
    r.add_argument("--between", type=_parse_between, metavar="HH:MM-HH:MM",
                   help="intra-day window, CT. Narrows what is REPORTED; the "
                        "detector still sees the whole day, because extrema "
                        "and cooldowns are path-dependent")
    r.add_argument("--rth", action="store_true",
                   help=f"shorthand for --between "
                        f"{RTH_WINDOW[0]:%H:%M}-{RTH_WINDOW[1]:%H:%M}, the cash "
                        f"session. Use this when comparing against a live log, "
                        f"which watches RTH; without it a replay covers the "
                        f"whole Globex session and legitimately reports more")
    r.add_argument("--price", dest="band", type=_parse_band, metavar="LOW-HIGH",
                   help="only report events from bars whose range touched this band")
    r.add_argument("--kind", action="append", default=[], choices=KNOWN_KINDS)
    r.add_argument("--subtype", action="append", default=[])
    r.add_argument("--sig", action="append", default=[], choices=KNOWN_SIGS)
    r.add_argument("-o", "--out", type=Path, help="jsonl out; stdout if omitted")
    r.add_argument("--knobs", type=Path, help="override config/tape_events.yaml")

    d = sub.add_parser("diff", help="compare two runs and count what moved")
    d.add_argument("before", type=Path)
    d.add_argument("after", type=Path)
    d.add_argument("--json", action="store_true", help="machine-readable")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.cmd == "diff":
        before = [json.loads(l) for l in args.before.read_text().splitlines() if l]
        after = [json.loads(l) for l in args.after.read_text().splitlines() if l]
        result = diff(before, after)
        print(json.dumps(result, indent=2) if args.json else render_diff(result))
        return 0 if result["identical"] else 1

    if args.rth and args.between:
        p.error("--rth and --between both set the same window; pick one")
    region = Region(
        start=args.start, end=args.end or args.start,
        between=RTH_WINDOW if args.rth else args.between,
        price_band=args.band,
    )
    if region.end < region.start:
        p.error("--to is before --from")
    filt = Filter(frozenset(args.kind), frozenset(args.subtype), frozenset(args.sig))
    knobs = load_knobs(args.knobs)
    log.info("knobs: %s", json.dumps(knobs_to_dict(knobs), sort_keys=True))

    records = replay(region, filt, knobs)
    payload = "\n".join(json.dumps(r, sort_keys=True) for r in records)
    if args.out:
        args.out.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        log.info("%d events -> %s", len(records), args.out)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
