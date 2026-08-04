#!/usr/bin/env python3
"""Grade the live continuation meter's own calls against the tape. [st-em4r]

The meter has journaled every frame it ever rendered and nobody had ever asked
whether those frames were right. The audit named that twice — as executive
summary item 6 ("the live meter has never graded a live market minute") and as
the systemic prescription in §4.4 ("verify the artifact, not the process": the
meter journal exists precisely so its calls can be scored, and the fact that
scoring has not happened is the same gap in a different costume). This script
is the missing half.

What it does
------------
For every frame in a day's journal it takes the probability the pane displayed,
reconstructs the event that probability was *about*, and resolves that event on
the tape — in path order, on raw ES ticks, so "did it pay before it cost" is
answered by which barrier arrived first rather than by a minute bar's high and
low. It then reports predicted-vs-realized by bucket.

It grades up to four claims per frame, whichever the frame carries:

  primary          the reworked pane's headline decision label, e.g.
                   reach5_before_adverse4 — pays N before it costs M, 15 min
  secondary        the convergence score against ITS label: extension >= 2 pts
                   beyond the standing extreme within 15 min
  legacy_sentence  what the pre-st-em4r pane's SENTENCE said — "extends 2+ pts
                   in the next 15 min", i.e. gain 2 pts from here
  legacy_number    what that pane's INTEGER was calibrated on — the standing
                   extreme label

The last two are graded from the retired 25/49/65/73 and 33/57/74 constants so
that journals written before the rework stay gradeable, and because scoring
both of them on the same frames is the live demonstration of audit §3.2: one
number, two different events, 35 points of base rate apart.

Honesty constraints this script enforces on itself
--------------------------------------------------
* **Overlapping windows.** Frames arrive every 30 s and each looks 15 minutes
  ahead, so ~30 consecutive frames share almost the same outcome. These are not
  independent trials; the summary prints the count of non-overlapping windows
  next to the frame count and refuses to print a p-value.
* **Truncated windows.** A frame whose 15 minutes run past the end of the tape
  can still resolve TRUE (the barrier was hit) but cannot resolve FALSE. Those
  are reported as `unresolved`, never as misses.
* **Instrument.** The meter watches $SPX cash minute closes; this scores on ES
  ticks, the instrument the truth table was measured on (audit §1.4 flags the
  mismatch). Barriers are point offsets from an ES anchor taken at the frame's
  own timestamp, so the cash/futures basis never enters the arithmetic.

Usage:
    .venv/bin/python3 scripts/measurement/score_meter_journal.py
    .venv/bin/python3 scripts/measurement/score_meter_journal.py --day 2026-08-04
    .venv/bin/python3 scripts/measurement/score_meter_journal.py --all-frames
    .venv/bin/python3 scripts/measurement/score_meter_journal.py --tape journal

Output: stdout summary + data/exec/continuation-meter-<day>-scored.json.
Exit 0 when at least one claim resolved, 1 when the journal is missing, empty
or unreadable, 2 when frames were present but none could be resolved against
the tape — a distinct code so "the meter was never live" (the 2026-08-03
journal: 729 after-hours frames on a frozen 14:59 candle, audit §1.6) is never
confused with "the meter was wrong".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from bisect import bisect_left
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from market.orderflow.replay import read_corpus_day  # noqa: E402

CT = ZoneInfo("America/Chicago")
EXEC_DIR = ROOT / "data" / "exec"
LOOKAHEAD_MIN = 15          # the meter's horizon, and the truth table's
EXT_PTS = 2.0               # the standing-extreme label's extension threshold

# Retired display constants. The pre-st-em4r pane rendered these as "about N%
# chance the move extends 2+ pts in the next 15 min"; st-em4r removed them from
# continuation_meter.py because that sentence named the wrong label. They live
# on HERE, and only here, so journals written before the rework can still be
# graded — both against the sentence they carried and against the label the
# number was actually calibrated on.
RETIRED_SCORE_P = {0: 0.25, 1: 0.49, 2: 0.65, 3: 0.73}
RETIRED_SCORE2_P = {0: 0.33, 1: 0.57, 2: 0.74}

# label_key -> (target_pts, stop_pts | None). Mirrors decision_aligned_study's
# label grammar; parsed rather than enumerated so a new N/M pair needs no edit.
_LABEL_RE = re.compile(r"^reach(?P<n>[0-9.]+)_"
                       r"(?:any_adverse|before_adverse(?P<m>[0-9.]+))$")


def parse_label(label: str) -> tuple[float, float | None] | None:
    """(target, stop) in points for a reachN[_before_adverseM] label, else None.

    `reachN_any_adverse` returns a stop of None — the target-only view, which
    ignores what the position endures on the way (and so flatters every hold).
    """
    m = _LABEL_RE.match(label or "")
    if not m:
        return None
    return float(m.group("n")), (float(m.group("m")) if m.group("m") else None)


# ---------------------------------------------------------------------------
# tape
# ---------------------------------------------------------------------------

class Tape:
    """A day's price path as parallel, time-sorted arrays.

    Two sources, in preference order. ES ticks resolve barriers in true path
    order, which is the only way "did it pay before it cost" has an answer. The
    journal's own $SPX samples are the degraded fallback for a day with no
    corpus file: 30-second resolution, so barrier ORDER inside a sample gap is
    unrecoverable and every read from it is marked as such.
    """

    def __init__(self, ts: list[datetime], px: list[float], source: str,
                 note: str = ""):
        self.ts, self.px, self.source, self.note = ts, px, source, note

    def __len__(self) -> int:
        return len(self.ts)

    @property
    def path_ordered(self) -> bool:
        return self.source == "es-ticks"

    def index_at(self, when: datetime) -> int:
        """First sample at or after ``when`` (== len(self) when past the end)."""
        return bisect_left(self.ts, when)

    def extreme(self, lo: datetime, hi: datetime, direction: int) -> float | None:
        """Running extreme in the move's direction over [lo, hi]. None if empty."""
        i, j = self.index_at(lo), self.index_at(hi)
        # include a sample landing exactly on hi
        while j < len(self.px) and self.ts[j] <= hi:
            j += 1
        if j <= i:
            return None
        window = self.px[i:j]
        return max(window) if direction == 1 else min(window)


def load_es_tape(day: date) -> Tape:
    trades = read_corpus_day(day)
    ts = [t.ts for t in trades]
    px = [t.price for t in trades]
    return Tape(ts, px, "es-ticks",
                f"{len(ts)} ES trades from data/corpus/{day}/")


def load_journal_tape(rows: list[dict]) -> Tape:
    """Degraded fallback: the meter's own $SPX samples, ~30 s apart."""
    pts = []
    for r in rows:
        spx = (r.get("levels") or {}).get("spx")
        if spx is None:
            continue
        try:
            pts.append((datetime.fromisoformat(r["ts"]), float(spx)))
        except (KeyError, TypeError, ValueError):
            continue
    pts.sort()
    return Tape([p[0] for p in pts], [p[1] for p in pts], "journal-spx-30s",
                f"{len(pts)} $SPX samples from the journal itself — 30-second "
                f"resolution, barrier order inside a gap is NOT recoverable")


# ---------------------------------------------------------------------------
# event resolution
# ---------------------------------------------------------------------------

def resolve_barrier(tape: Tape, start: datetime, anchor: float, direction: int,
                    target: float, stop: float | None) -> tuple[bool | None, dict]:
    """Did price make ``target`` before losing ``stop``, within the horizon?

    Returns (outcome, detail). ``outcome`` is True / False / None, where None
    means the window ran past the end of the tape without either barrier being
    touched — unknowable, and reported as unresolved rather than as a miss. A
    stop-first is knowable even on a truncated window, so it returns False.

    With ``stop=None`` this is the target-only label: True as soon as the target
    prints, False only if the full window completed without it.

    One definitional note against the study. `decision_aligned_study` anchors on
    a minute's close and opens its window at the following minute boundary; a
    live frame arrives mid-minute, so this opens the window at the frame's own
    timestamp. Both start at the anchor price; this one simply does not discard
    the remainder of the anchor minute, which for a frame is the wrong thing to
    discard — the position exists from that instant.
    """
    end = start + timedelta(minutes=LOOKAHEAD_MIN)
    i, j = tape.index_at(start), tape.index_at(end)
    truncated = (j >= len(tape) and (not tape.ts or tape.ts[-1] < end))
    hit_t = hit_s = None
    for k in range(i, j):
        exc = (tape.px[k] - anchor) * direction
        if hit_t is None and exc >= target:
            hit_t = k
            break                       # target first — nothing later can change it
        if stop is not None and hit_s is None and -exc >= stop:
            hit_s = k
            break                       # stop first — likewise
    detail = dict(truncated=truncated, samples=max(0, j - i),
                  hit_target_at=(tape.ts[hit_t].isoformat() if hit_t is not None
                                 else None),
                  hit_stop_at=(tape.ts[hit_s].isoformat() if hit_s is not None
                               else None))
    if hit_t is not None:
        return True, detail
    if hit_s is not None:
        return False, detail
    return (None, detail) if truncated else (False, detail)


def resolve_standing_extreme(tape: Tape, start: datetime, move_start: datetime,
                             direction: int) -> tuple[bool | None, dict]:
    """The program's original label, resolved live: a NEW extreme +2 pts out.

    The standing extreme is recomputed from the tape over [move start, frame
    time] rather than lifted from the frame's $SPX numbers, so the cash/futures
    basis never enters — the whole comparison happens in one instrument.
    """
    ext = tape.extreme(min(move_start, start), start, direction)
    if ext is None:
        return None, dict(reason="no tape before this frame")
    outcome, detail = resolve_barrier(
        tape, start, ext, direction, EXT_PTS, None)
    detail["standing_extreme"] = round(ext, 2)
    return outcome, detail


# ---------------------------------------------------------------------------
# per-frame grading
# ---------------------------------------------------------------------------

def claims_of(frame: dict) -> list[dict]:
    """Every probability this frame put on the screen, with the event it named.

    A claim is {name, p, label, target, stop, source}. Frames from before the
    st-em4r rework carry only a score, and are graded twice — once against the
    sentence that pane displayed and once against the label its integer came
    from. That pair IS audit §3.2, measured on live frames.
    """
    out: list[dict] = []
    prim = frame.get("primary") or {}
    if prim.get("p") is not None and prim.get("label"):
        parsed = parse_label(prim["label"])
        if parsed:
            out.append(dict(name="primary", p=prim["p"], label=prim["label"],
                            target=parsed[0], stop=parsed[1],
                            bucket=f"{prim.get('family')}:{prim.get('bucket')}",
                            source="displayed headline"))
    sec = frame.get("secondary") or {}
    if sec.get("p") is not None and sec.get("label"):
        out.append(dict(name="secondary", p=sec["p"], label=sec["label"],
                        target=None, stop=None,
                        bucket=f"score{sec.get('mode')}={sec.get('score')}",
                        source="displayed convergence score"))
    score, mode = frame.get("score"), frame.get("score_mode")
    if score is not None and mode in (2, 3) and not sec:
        table = RETIRED_SCORE_P if mode == 3 else RETIRED_SCORE2_P
        p = table.get(score)
        if p is not None:
            out.append(dict(name="legacy_sentence", p=p,
                            label="reach2_any_adverse", target=2.0, stop=None,
                            bucket=f"score{mode}={score}",
                            source="retired pane sentence "
                                   "('extends 2+ pts in the next 15 min')"))
            out.append(dict(name="legacy_number", p=p,
                            label="orig_ext2_beyond_standing_extreme",
                            target=None, stop=None,
                            bucket=f"score{mode}={score}",
                            source="retired pane integer "
                                   "(calibrated on the standing-extreme label)"))
    return out


def grade_frame(frame: dict, tape: Tape) -> dict | None:
    """Resolve every claim in one frame. None when the frame carries no move."""
    if frame.get("preopen") or frame.get("no_data"):
        return None
    mv = frame.get("move")
    if not mv or mv.get("dir") is None:
        return None
    try:
        ts = datetime.fromisoformat(frame["ts"])
        move_start = datetime.fromisoformat(mv["start_t"]) \
            if isinstance(mv["start_t"], str) else mv["start_t"]
    except (KeyError, TypeError, ValueError) as e:
        return dict(error=f"unparseable frame timestamps: {e}")
    direction = int(mv["dir"])
    i = tape.index_at(ts)
    if i >= len(tape):
        return dict(ts=frame["ts"], skipped="no tape at or after this frame")
    anchor = tape.px[i]

    graded = []
    for c in claims_of(frame):
        if c["label"] == "orig_ext2_beyond_standing_extreme":
            outcome, detail = resolve_standing_extreme(
                tape, ts, move_start, direction)
        else:
            outcome, detail = resolve_barrier(
                tape, ts, anchor, direction, c["target"], c["stop"])
        graded.append(dict(c, outcome=outcome, **detail))
    return dict(ts=frame["ts"], dir=direction, anchor=round(anchor, 2),
                move_size=mv.get("size"),
                contested=bool(mv.get("contested")),
                dir_flip=bool(frame.get("dir_flip")),
                stale_min=frame.get("stale_min"),
                buckets=frame.get("buckets"), claims=graded)


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------

def independent_windows(rows: list[dict]) -> int:
    """How many non-overlapping 15-minute windows the graded frames cover.

    The honest denominator. 230 frames over 2h20 is ~9 independent looks at the
    tape, not 230, and every summary line prints both numbers side by side.
    """
    stamps = sorted(datetime.fromisoformat(r["ts"]) for r in rows if "ts" in r)
    n, last = 0, None
    for t in stamps:
        if last is None or (t - last).total_seconds() >= LOOKAHEAD_MIN * 60:
            n += 1
            last = t
    return n


def _cell(items: list[tuple[float, bool | None]]) -> dict:
    """n / resolved / predicted / realized / gap / Brier for one group.

    ``predicted`` averages only the frames that resolved, so it describes the
    same frames ``realized`` does and ``gap`` is a like-for-like difference.
    ``predicted_all`` keeps the average over every frame in the group, which is
    the one a reader would compute by hand off the pane.
    """
    resolved = [(p, o) for p, o in items if o is not None]
    out = dict(n=len(items), n_resolved=len(resolved),
               predicted_all=round(mean(p for p, _ in items), 4) if items else None)
    out["predicted"] = out["predicted_all"]
    if resolved:
        out["predicted"] = round(mean(p for p, _ in resolved), 4)
        out["realized"] = round(mean(1.0 if o else 0.0 for _, o in resolved), 4)
        out["gap"] = round(out["realized"] - out["predicted"], 4)
        out["brier"] = round(mean((p - (1.0 if o else 0.0)) ** 2
                                  for p, o in resolved), 4)
    return out


def calibration(rows: list[dict]) -> dict:
    """predicted-vs-realized per claim, overall and per displayed bucket."""
    by_claim: dict[str, dict] = {}
    for r in rows:
        for c in r.get("claims", ()):
            slot = by_claim.setdefault(c["name"], dict(
                label=c["label"], source=c["source"], items=[], buckets={}))
            slot["items"].append((c["p"], c["outcome"]))
            slot["buckets"].setdefault(c["bucket"], []).append(
                (c["p"], c["outcome"]))
    out = {}
    for name, slot in by_claim.items():
        out[name] = dict(label=slot["label"], source=slot["source"],
                         overall=_cell(slot["items"]),
                         by_bucket={b: _cell(v)
                                    for b, v in sorted(slot["buckets"].items())})
    return out


# ---------------------------------------------------------------------------
# io / cli
# ---------------------------------------------------------------------------

def read_journal(path: Path) -> list[dict]:
    rows, bad = [], 0
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
                print(f"  {path.name}:{lineno} unparseable frame — skipped",
                      file=sys.stderr)
    if bad:
        print(f"  {bad} unparseable frame(s) in {path.name}", file=sys.stderr)
    return rows


def dedup_by_minute(rows: list[dict]) -> list[dict]:
    """First frame of each wall-clock minute.

    The meter renders twice a minute; two frames 30 s apart share ~97% of their
    forward window. Keeping one per minute does not make the sample independent
    (see ``independent_windows``) — it stops the same minute being counted
    twice, which is a different and smaller problem.
    """
    seen, out = set(), []
    for r in rows:
        try:
            key = datetime.fromisoformat(r["ts"]).replace(second=0,
                                                          microsecond=0)
        except (KeyError, TypeError, ValueError):
            out.append(r)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def render_report(report: dict) -> str:
    m = report["meta"]
    L = [f"METER JOURNAL SCORECARD — {m['day']}",
         f"  journal   {m['journal']}",
         f"  frames    {m['n_frames']} in file · {m['n_considered']} considered · "
         f"{m['n_graded']} graded",
         f"  tape      {m['tape_source']} — {m['tape_note']}",
         f"  windows   {m['independent_windows']} non-overlapping 15-min windows "
         f"behind those {m['n_graded']} frames"]
    if m.get("n_contested"):
        L.append(f"  direction {m['n_contested']} frame(s) flagged CONTESTED, "
                 f"{m['n_dir_flips']} direction flip(s)")
    if m.get("n_stale"):
        L.append(f"  staleness {m['n_stale']} frame(s) rendered on a candle "
                 f"older than 3 min")
    if not m["path_ordered"]:
        L.append("  !! barriers resolved on 30-second samples — which barrier "
                 "came FIRST is not recoverable")
    for reason, n in sorted(m.get("skip_reasons", {}).items(),
                            key=lambda kv: -kv[1]):
        L.append(f"  skipped   {n:>5}  {reason}")
    L.append("")
    if not report["calibration"]:
        L.append("No claim in any frame could be graded. Nothing to calibrate.")
        for note in report["notes"]:
            L.append(f"NOTE  {note}")
        return "\n".join(L)
    for name, c in report["calibration"].items():
        o = c["overall"]
        L.append(f"[{name}]  {c['label']}")
        L.append(f"  {c['source']}")
        if o.get("realized") is None:
            L.append(f"  {o['n']} frames, 0 resolved — the forward tape ends "
                     f"before their windows close.")
            L.append("")
            continue
        L.append(f"  predicted {o['predicted']:.3f}   realized "
                 f"{o['realized']:.3f}   gap {o['gap']:+.3f}   "
                 f"Brier {o['brier']:.3f}   "
                 f"(n={o['n']}, resolved={o['n_resolved']})")
        L.append(f"  {'bucket':<22} {'n':>5} {'res':>5} {'pred':>7} "
                 f"{'real':>7} {'gap':>7}")
        for b, cell in c["by_bucket"].items():
            real = ("     —" if cell.get("realized") is None
                    else f"{cell['realized']:7.3f}")
            gap = ("     —" if cell.get("gap") is None
                   else f"{cell['gap']:+7.3f}")
            L.append(f"  {b:<22} {cell['n']:>5} {cell['n_resolved']:>5} "
                     f"{cell['predicted']:7.3f} {real} {gap}")
        L.append("")
    for note in report["notes"]:
        L.append(f"NOTE  {note}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", help="YYYY-MM-DD (default: today, CT)")
    ap.add_argument("--journal", type=Path, help="explicit journal path")
    ap.add_argument("--out", type=Path, help="explicit output JSON path")
    ap.add_argument("--tape", choices=("auto", "es", "journal"), default="auto",
                    help="price source for resolution (default auto: ES ticks "
                         "when the corpus day exists, else the journal's own "
                         "$SPX samples)")
    ap.add_argument("--all-frames", action="store_true",
                    help="grade every frame instead of one per minute")
    args = ap.parse_args()

    day = (date.fromisoformat(args.day) if args.day
           else datetime.now(tz=CT).date())
    journal = args.journal or EXEC_DIR / f"continuation-meter-{day}.jsonl"
    if not journal.exists():
        print(f"No journal at {journal}", file=sys.stderr)
        return 1
    rows = read_journal(journal)
    if not rows:
        print(f"{journal} is empty", file=sys.stderr)
        return 1

    notes: list[str] = []
    tape: Tape | None = None
    if args.tape in ("auto", "es"):
        try:
            tape = load_es_tape(day)
        except FileNotFoundError as e:
            if args.tape == "es":
                print(f"No ES corpus for {day}: {e}", file=sys.stderr)
                return 1
            notes.append(f"No ES corpus for {day} — fell back to the journal's "
                         f"own $SPX samples; barrier ORDER is not recoverable "
                         f"from 30-second data.")
        except Exception as e:                  # unreadable / malformed corpus
            if args.tape == "es":
                print(f"ES corpus unreadable for {day}: {e}", file=sys.stderr)
                return 1
            notes.append(f"ES corpus unreadable for {day} ({e}) — fell back to "
                         f"the journal's own $SPX samples.")
    if tape is None or args.tape == "journal":
        tape = load_journal_tape(rows)
    if not len(tape):
        print(f"No usable price data for {day} from any source", file=sys.stderr)
        return 1

    considered = rows if args.all_frames else dedup_by_minute(rows)
    graded: list[dict] = []
    skips: dict[str, int] = {}

    def _skip(reason: str) -> None:
        skips[reason] = skips.get(reason, 0) + 1

    for f in considered:
        try:
            g = grade_frame(f, tape)
        except Exception as e:                  # one bad frame must not lose the run
            print(f"  frame {f.get('ts')} failed to grade: {e}", file=sys.stderr)
            _skip("grading raised")
            continue
        if g is None:
            _skip("pre-open / no-data / no move")
        elif g.get("skipped"):
            _skip(g["skipped"])
        elif g.get("error"):
            _skip(g["error"])
        elif not g["claims"]:
            _skip("frame displayed no probability")
        else:
            graded.append(g)
    skipped = sum(skips.values())

    n_resolved = sum(1 for g in graded for c in g["claims"]
                     if c["outcome"] is not None)
    if not n_resolved and considered:
        notes.append(f"Nothing in this journal could be graded: the tape ends "
                     f"{tape.ts[-1].strftime('%H:%M') if len(tape) else '?'} and "
                     f"{skipped} of {len(considered)} frames sit at or past it. "
                     f"That is what an after-hours run looks like — frames "
                     f"rendered, nothing forward to grade them against "
                     f"(audit §1.6).")
    notes.append("Frames overlap — each looks 15 minutes ahead and they arrive "
                 "every 30 s, so consecutive frames share almost the same "
                 "outcome. Read these as descriptive; no significance test is "
                 "reported because the sample does not support one.")
    notes.append("Resolution instrument is ES; the meter watches $SPX cash "
                 "(audit §1.4). Barriers are point offsets from an ES anchor at "
                 "the frame's own timestamp, so the basis does not enter.")

    report = dict(
        schema=dict(
            meta="run provenance: day, journal, tape source, frame counts",
            frames="per-frame grading: anchor, direction, and every claim the "
                   "frame displayed with its resolved outcome "
                   "(True / False / null = window ran past the tape)",
            calibration="claim -> {overall, by_bucket} with predicted, "
                        "realized, gap and Brier score",
            notes="constraints a reader must carry into these numbers"),
        meta=dict(
            bead="st-em4r", day=day.isoformat(), journal=str(journal),
            generated=datetime.now(tz=CT).isoformat(timespec="seconds"),
            n_frames=len(rows), n_considered=len(considered),
            n_graded=len(graded), n_skipped=skipped, skip_reasons=skips,
            n_claims=sum(len(g["claims"]) for g in graded),
            n_resolved_claims=n_resolved,
            dedup="one frame per minute" if not args.all_frames else "every frame",
            tape_source=tape.source, tape_note=tape.note,
            path_ordered=tape.path_ordered,
            lookahead_min=LOOKAHEAD_MIN,
            independent_windows=independent_windows(graded),
            n_contested=sum(1 for g in graded if g.get("contested")),
            n_dir_flips=sum(1 for g in graded if g.get("dir_flip")),
            n_stale=sum(1 for g in graded if (g.get("stale_min") or 0) > 3)),
        frames=graded,
        calibration=calibration(graded),
        notes=notes)

    out_path = args.out or journal.with_name(journal.stem + "-scored.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(render_report(report))
    print(f"\nwrote {out_path}")
    return 0 if n_resolved else 2


if __name__ == "__main__":
    sys.exit(main())
