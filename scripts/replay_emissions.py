#!/usr/bin/env python3
"""Re-emit archived tape through current code, diff two such runs, count.

Desk Ruling 9 (memo 20260826T012334, from Steve direct): *the replayability of
verbatim current code against the historical datastore is a core property of
this estate; leverage it always when possible, and ensure updates do not
degrade it.* Every change touching an emission or detection path ships with a
re-emission diff over archived tape as its review artifact — a silent-intent
change proves byte-identical, a behavior change presents the diff as the
evidence, counted.

That capability existed only as artisanal practice: whoever ran the two-tier
cutover proof, the sweep census, the rolling-window evidence gate each built it
by hand for one occasion. This is co-b18wf, the runner. The engine lives in
``market/orderflow/region_replay.py`` — this file is its command line and the
process ``scripts/drill_bridge.py`` shells out to for the FootPrint page's
region replay (co-j9t1g). One engine, three doors; see that module's docstring.

TWO PATHS. ``--path tape`` is the one-minute tape-event path (PLAN-LEVEL,
SUPERLATIVE, CLIMAX, ABSORPTION-CLUSTER — what ``live_effort_effect.py``
logs); ``--path engine`` is the volume-bar stack (sweeps, stacks, divergences,
setups — what the FootPrint feeder emits), driven the live way. Default is
both; a ``--kind`` filter runs only the path that can produce it.

DETERMINISM. Nothing here reads a wall clock. Every decision keys off the
trade timestamp, the same property ``LiveScorer`` documents and the parity
harness depends on. Two runs over one region with unchanged code are
byte-identical, or this tool is broken and the diff it produces means nothing.

WHAT IS PROVEN. Read this before quoting a number from it.

*Proven:* two runs of this tool over one region are byte-identical with
unchanged code, and a code change shows up as a counted diff.

*Also proven, 2026-08-26 (st-v3wj):* a replay reproduces what the live emitter
actually said. 2026-08-25 is the one day with both a full live log and an
archive, and the tape path reproduces it exactly — 102 EVENT lines against the
102 in ``/var/moo/logs/effort-effect/2026-08-25.log``, compared line by line,
all 102 byte-identical, PLAN-LEVEL 37/28/10 = 75 either way::

    scripts/replay_emissions.py run --from 2026-08-25 --path tape -o r.jsonl
    # then compare each row's "line" field against the log's EVENT lines

THE EARLIER MISMATCH WAS A BAD BASELINE, not a defect in this tool. This
docstring used to record the live side as 74 events and name the anchor set as
the suspect. That 74 was a PARTIAL-DAY count copied from a mid-session census.
Nothing was ever wrong with the anchor set.

The near miss worth remembering: ``scripts/live_footprint_feed.py`` genuinely
DID run 08-25 with zero anchors (st-kxnv, a real and separate bug), and its
``live-parity`` run row records ``mancini: []``. That is a different process
from the scorer. A zero in the feeder's run row says nothing about the
scorer's log.

USE — prove a change silent::

    scripts/replay_emissions.py run --from 2026-08-01 --to 2026-08-25 -o before.jsonl
    # ... make the change ...
    scripts/replay_emissions.py run --from 2026-08-01 --to 2026-08-25 -o after.jsonl
    scripts/replay_emissions.py diff before.jsonl after.jsonl

USE — scope to what you are actually changing::

    scripts/replay_emissions.py run --from 2026-08-25 \\
        --kind PLAN-LEVEL --between 13:30-15:00 -o pm.jsonl

USE — say it (the spoken door; the same sentence the page and the intent
dialect take)::

    scripts/replay_emissions.py run --say "Monday 13:30 to 14:10, sweeps and plan-level only"
    scripts/replay_emissions.py run --say "yesterday first hour" --json

``--json`` prints one object — the request as understood, its read-back, the
count and the records — which is what the bridge consumes. ``kinds`` prints
the filter vocabulary the same way.

Bead: co-b18wf. Surface: co-j9t1g.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date, datetime, time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market.orderflow.region_replay import (  # noqa: E402,F401 — re-exported for tests and callers
    KNOWN_KINDS, KNOWN_SIGS, PATH_OF, PATHS, RTH_WINDOW, SUBJECT_FIELDS, Filter, Region,
    _key, diff, render_diff, replay, replay_day, resolve_kinds, vocabulary,
)
from market.orderflow.tape_events import knobs_to_dict, load_knobs  # noqa: E402

log = logging.getLogger("replay_emissions")


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


def build_request(args) -> tuple[Region, Filter, dict]:
    """Flags plus an optional sentence → region, filter, and the request as
    understood (for ``--json`` and the read-back). Explicit flags win over
    what the sentence said; the sentence fills what the flags left unset."""
    said: dict = {}
    if args.say:
        from strader.intent.replay import parse_replay, readback
        req = parse_replay(args.say, default_day=args.start)
        said = req.as_dict()
        said["readback"] = readback(req)
        start = args.start or req.day
        end = args.end or req.end or start
        between = args.between or req.between
        band = args.band or req.price_band
        kinds = frozenset(args.kind) or req.kinds
    else:
        if args.start is None:
            raise SystemExit("run: --from or --say is required")
        start, end = args.start, args.end or args.start
        between, band, kinds = args.between, args.band, frozenset(args.kind)
    if args.rth:
        between = RTH_WINDOW
    region = Region(start=start, end=end, between=between, price_band=band)
    if region.end < region.start:
        raise SystemExit("run: --to is before --from")
    filt = Filter(kinds, frozenset(args.subtype), frozenset(args.sig))
    if args.path:
        # Restrict to the named paths on top of what the kinds imply.
        keep = tuple(p for p in filt.paths() if p in set(args.path))
        if not keep:
            raise SystemExit(f"run: --path {args.path} produces none of the kinds asked for")
        filt = Filter(kinds or frozenset(k for k in KNOWN_KINDS if PATH_OF[k] in keep),
                      filt.subtypes, filt.sigs)
    said.update({"region": region.describe(), "filter": filt.describe()})
    return region, filt, said


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="re-emit a region of archived tape")
    r.add_argument("--from", dest="start", type=_parse_day, metavar="YYYY-MM-DD",
                   help="first day; required unless --say names one")
    r.add_argument("--to", dest="end", type=_parse_day, metavar="YYYY-MM-DD",
                   help="defaults to --from, i.e. a single day")
    r.add_argument("--say", metavar="SENTENCE",
                   help="the spoken form: 'Monday 13:30 to 14:10, sweeps and plan-level only'. "
                        "Flags given alongside override what the sentence said")
    r.add_argument("--between", type=_parse_between, metavar="HH:MM-HH:MM",
                   help="intra-day window, CT. Narrows what is REPORTED; the "
                        "detectors still see the whole day, because extrema "
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
    r.add_argument("--path", action="append", default=[], choices=PATHS,
                   help="tape (minute events) and/or engine (volume-bar stack); default both")
    r.add_argument("-o", "--out", type=Path, help="jsonl out; stdout if omitted")
    r.add_argument("--json", action="store_true",
                   help="one JSON object on stdout: request, readback, count, records")
    r.add_argument("--knobs", type=Path, help="override config/tape_events.yaml")

    d = sub.add_parser("diff", help="compare two runs and count what moved")
    d.add_argument("before", type=Path)
    d.add_argument("after", type=Path)
    d.add_argument("--json", action="store_true", help="machine-readable")

    k = sub.add_parser("kinds", help="the filter vocabulary: kinds, the words that name them, sigs")
    k.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    # --json owns stdout; everything else goes to stderr so the consumer can parse it.
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        stream=sys.stderr if getattr(args, "json", False) else None)

    if args.cmd == "kinds":
        v = vocabulary()
        if args.json:
            print(json.dumps(v, sort_keys=True))
        else:
            for kd in v["kinds"]:
                words = [w for w, ks in v["words"].items() if kd["id"] in ks]
                print(f"{kd['id']:<20} {kd['path']:<7} {kd['label']:<20} said as: {', '.join(words)}")
        return 0

    if args.cmd == "diff":
        before = [json.loads(l) for l in args.before.read_text().splitlines() if l]
        after = [json.loads(l) for l in args.after.read_text().splitlines() if l]
        result = diff(before, after)
        print(json.dumps(result, indent=2) if args.json else render_diff(result))
        return 0 if result["identical"] else 1

    if args.rth and args.between:
        p.error("--rth and --between both set the same window; pick one")
    try:
        region, filt, said = build_request(args)
    except SystemExit as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
            return 2
        raise
    except ValueError as e:      # ReplayParseError is one
        if args.json:
            print(json.dumps({"error": str(e), "say": args.say}))
            return 2
        p.error(str(e))
    knobs = load_knobs(args.knobs)
    log.info("knobs: %s", json.dumps(knobs_to_dict(knobs), sort_keys=True))
    log.info("region: %s  filter: %s", region.describe(), filt.describe())

    records = replay(region, filt, knobs)
    if args.json:
        print(json.dumps({"request": said, "count": len(records), "records": records},
                         sort_keys=True))
        return 0
    payload = "\n".join(json.dumps(r, sort_keys=True) for r in records)
    if args.out:
        args.out.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        log.info("%d events -> %s", len(records), args.out)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
