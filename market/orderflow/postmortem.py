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
    lid_ticks: int = 8            # Addendum A3: a high this close under the level is a lid rejection
    lid_window_min: int = 30      # Addendum A3: look-back for lid rejections and window delta


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
    run: int = 1            # the feeder run that wrote it (bar numbers restart per run)

    @classmethod
    def from_record(cls, rec: dict, run: int = 1) -> "Bar":
        return cls(i=int(rec["i"]),
                   t0=datetime.fromisoformat(rec["t0"]),
                   t1=datetime.fromisoformat(rec["t1"]),
                   o=float(rec["o"]), h=float(rec["h"]), l=float(rec["l"]),
                   c=float(rec["c"]), v=int(rec["v"]), d=int(rec["d"]), run=run)


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
        self._pos = {(b.run, b.i): k for k, b in enumerate(self.bars)}

    def pos(self, bar_i, run: int | None = None) -> int | None:
        """List index of feeder bar ``bar_i`` of ``run`` (this segment's run
        when not given). Bar numbers restart at every feeder run, so a
        stitched day keys on both."""
        if bar_i is None:
            return None
        return self._pos.get((self.run_no if run is None else int(run), int(bar_i)))

    def pos_of(self, ev: dict) -> int | None:
        return self.pos(ev.get("bar_i"), ev.get("run"))

    @property
    def mancini(self) -> list[float]:
        return [float(x) for x in (self.meta.get("mancini") or [])]

    @property
    def anchorless(self) -> bool:
        """Addendum A2: the run's header carried no Mancini levels (a restart
        before the morning parse landed). No calls there is not nothing to call."""
        return not self.mancini

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
        out.append(Segment(run_no=n, bars=[Bar.from_record(b, run=n) for b in run.bars],
                           events=[dict(e, run=n) for e in run.events],
                           meta=run.meta, complete=run.complete))
    return out


def segments_from_replay(day: _date, *, bar_n: int, mancini: list[float]) -> list[Segment]:
    """One Segment from a full replay of the day's tape (backfill path)."""
    from market.orderflow.replay_live import replay_events
    bars, events = replay_events(day, bar_n=bar_n, mancini=mancini)
    if not bars:
        return []
    meta = {"bar_n": bar_n, "mancini": list(mancini), "started": bars[0]["t0"],
            "replay": True}
    return [Segment(run_no=1, bars=[Bar.from_record(b, run=1) for b in bars],
                    events=[dict(e, run=1) for e in events], meta=meta, complete=True)]


def stitch(segments: list[Segment]) -> Segment | None:
    """One Segment for the day from a run's worth of restarts.

    A feeder restart re-walks the tape from the day's start (catch-up), so a
    later run's record repeats every bar an earlier run already showed live;
    measured per run, the overlap counts twice (08-18: runs 10 and 11 both
    cover 02:50→13:01). Each run keeps only the bars after the last bar kept
    so far — what was on the screen at the time — with its events on those
    bars. Events with no bar (the ``Level`` announcements a run makes at
    start) are kept once per distinct (type, price, level_type). Each kept
    bar and event still names its run, so the page's ``run:bar`` is the
    file's. ``meta["overlap_bars"]`` records, per run, how many bars were
    dropped as re-walked. None when there is nothing to stitch.
    """
    if not segments:
        return None
    bars: list[Bar] = []
    events: list[dict] = []
    seen_nobar: set = set()
    overlap: dict[int, int] = {}
    last_t1: datetime | None = None
    for seg in segments:
        kept = [b for b in seg.bars if last_t1 is None or b.t0 >= last_t1]
        overlap[seg.run_no] = len(seg.bars) - len(kept)
        kept_keys = {(b.run, b.i) for b in kept}
        for e in seg.events:
            if e.get("bar_i") is None:
                key = (e.get("type"), e.get("price"), e.get("level_type"))
                if key in seen_nobar:
                    continue
                seen_nobar.add(key)
                events.append(e)
            elif (e.get("run", seg.run_no), int(e["bar_i"])) in kept_keys:
                events.append(e)
        bars += kept
        if kept:
            last_t1 = kept[-1].t1
    mancini = sorted({a for seg in segments for a in seg.mancini})
    meta = {"bar_n": segments[0].bar_n, "mancini": mancini, "started": segments[0].started,
            "overlap_bars": overlap, "stitched_runs": [seg.run_no for seg in segments]}
    return Segment(run_no=segments[0].run_no, bars=bars, events=events, meta=meta,
                   complete=segments[-1].complete)


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
    k = seg.pos_of(ev)
    if k is None:
        return None, None
    anchor = float(ev["anchor_price"])
    direction = ev.get("bias") or "bullish"
    pts = round(_sign(direction) * (seg.bars[k].c - anchor), 2)
    key = (ev.get("anchor_price"), ev.get("setup"), ev.get("fire_index"))
    forming_pos = [seg.pos_of(e) for e in seg.events
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


def measure_calls(seg: Segment, knobs: Knobs,
                  parsed_kinds: dict[float, str] | None = None) -> list[dict]:
    """One row per measured emission (spec §3a). ``forming`` beats and
    ``Level`` rows are not measured; events without a known bar are skipped
    (end-of-stream flush signals, profile levels).

    ``parsed_kinds`` (Addendum A1) is {price: kind} from the day's Mancini
    parse; every SetupRecognition row carries ``anchor_kind_parse`` — the
    parse's word for the anchor, or None when the parse has no such level.
    """
    rows: list[dict] = []
    parsed_kinds = parsed_kinds or {}
    for ev in seg.events:
        if ev.get("type") not in MEASURED_TYPES:
            continue
        if ev.get("type") == "SetupRecognition" and ev.get("state") == "forming":
            continue
        k = seg.pos_of(ev)
        if k is None:
            continue
        direction = direction_of(ev)
        if direction not in ("bullish", "bearish"):
            continue
        bar = seg.bars[k]
        entry = float(ev.get("start_price", bar.c)) if ev["type"] == "SweepPrint" else bar.c
        anchor = float(ev["anchor_price"]) if ev.get("anchor_price") is not None else None
        row = {
            "run": bar.run, "bar_i": bar.i, "ct": bar.t1.strftime("%H:%M"),
            "t1": bar.t1.isoformat(), "type": ev["type"],
            "setup": ev.get("setup"), "state": ev.get("state"),
            "direction": direction, "entry": entry,
            "confidence": ev.get("confidence"), "reason": ev.get("reason"),
            "anchor": anchor,
            "anchor_kind": ev.get("anchor_kind"),
            "anchor_kind_parse": (parsed_kinds.get(anchor) if anchor is not None else None),
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
        if ev["type"] == "SetupRecognition" and anchor is not None:
            if ev.get("state") == "confirmed":
                row["confirm_lag_bars"], row["confirm_lag_pts"] = confirm_lag(seg, ev)
            row["back_to_level_min"] = back_to_level(
                seg, k, anchor, direction,
                bar.t1 + timedelta(minutes=max(knobs.windows_min)))
            # Addendum A3 at the call: the lid under the anchor and the delta
            # in the window before the bar the setup fired on.
            row.update(lid_and_absorption(seg, k, direction, anchor, knobs))
        rows.append(row)
    return rows


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


def lid_and_absorption(seg: Segment, origin_i: int, direction: str,
                       level: float | None, knobs: Knobs) -> dict:
    """Addendum A3 — two bar-measurable facts from the ``lid_window_min``
    minutes before a leg's origin (bars strictly before the origin bar):

    ``lid_rejections``: bars whose high landed within ``lid_ticks`` under the
    level and closed under it (bullish legs; mirrored for bearish). A high
    exactly on the level counts — on a quarter-tick grid a touch that did not
    get through is a rejection. None when no level is within ``z_pts``.
    ``window_delta``: the bars' ``d`` summed. ``window_px_change``: the origin
    close minus the close at the start of the window (the last bar at or
    before it, else the first bar inside it). Absorption reads as delta one
    way while price went nowhere; the numbers are shown, not named.
    """
    o = seg.bars[origin_i]
    since = o.t1 - timedelta(minutes=knobs.lid_window_min)
    window = [b for b in seg.bars[:origin_i] if b.t1 >= since]
    before = [b for b in seg.bars[:origin_i] if b.t1 < since]
    out = {"lid_rejections": None, "window_delta": None, "window_px_change": None}
    if not window:
        return out
    out["window_delta"] = int(sum(b.d for b in window))
    ref = before[-1] if before else window[0]
    out["window_px_change"] = round(o.c - ref.c, 2)
    if level is None:
        return out
    band = knobs.lid_ticks * 0.25
    if direction == "bullish":
        n = sum(1 for b in window if level - band <= b.h <= level and b.c < level)
    else:
        n = sum(1 for b in window if level <= b.l <= level + band and b.c > level)
    out["lid_rejections"] = n
    return out


def tag_legs(legs: list[Leg], seg: Segment, *, anchors: list[float], knobs: Knobs) -> list[dict]:
    """Spec §3b steps 3–5: nearest level at the origin, and what was said in
    the W minutes before it, in the leg's direction. Plus Addendum A3's lid
    and absorption numbers on every row."""
    out: list[dict] = []
    for leg in legs:
        o = seg.bars[leg.origin_i]
        nearest, dist = None, None
        for a in anchors:
            d = abs(a - leg.origin_px)
            if dist is None or d < dist:
                nearest, dist = a, round(d, 2)
        near = dist is not None and dist <= knobs.z_pts
        since = o.t1 - timedelta(minutes=knobs.w_min)
        said: list[str] = []
        tag = "silent"
        for ev in seg.events:
            if ev.get("type") not in MEASURED_TYPES:
                continue
            k = seg.pos_of(ev)
            if k is None:
                continue
            t = seg.bars[k].t1
            if t < since or t > o.t1:
                continue
            if direction_of(ev) != leg.direction:
                continue
            if ev["type"] == "SetupRecognition":
                said.append(f"{ev.get('setup')} {ev.get('state')} @{float(ev.get('anchor_price') or 0):g} "
                            f"{t.strftime('%H:%M')}")
            else:
                said.append(f"{ev['type']} {t.strftime('%H:%M')}")
            if ev["type"] == "SetupRecognition" and ev.get("state") == "confirmed":
                tag = "called"
            elif tag != "called":
                tag = "hinted"
        row = {
            "run": o.run, "direction": leg.direction,
            "origin_bar": o.i, "origin_ct": o.t1.strftime("%H:%M"),
            "end_bar": seg.bars[leg.end_i].i, "end_ct": seg.bars[leg.end_i].t1.strftime("%H:%M"),
            "origin_px": leg.origin_px, "end_px": leg.end_px, "pts": leg.pts,
            "minutes": leg.minutes, "reached_x_min": leg.reached_x_min,
            "nearest_level": nearest, "level_distance": dist,
            "near_level": near,
            "tag": tag, "said_before": said,
        }
        row.update(lid_and_absorption(seg, leg.origin_i, leg.direction,
                                      nearest if near else None, knobs))
        out.append(row)
    return out


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
    from mancini.parser import extract_section
    section = extract_section(letter_text, RECAP_START, list(RECAP_END))
    if not section:
        return []
    rows: list[dict] = []
    for s in _recap_sentences(section):
        low = s.lower()
        hit = next(((low.find(word), code) for word, code in SETUP_WORDS if word in low), None)
        if not hit:
            continue
        at, setup = hit
        levels = [float(m) for m in re.findall(r"\b([5-9]\d{3})\b", s)]
        if not levels:
            continue
        t = _time_nearest(s, at)
        for lv in dict.fromkeys(levels):
            rows.append({"letter_date": letter_date.isoformat(), "setup": setup,
                         "level": lv, "time_et": t, "quote": s.strip()[:300]})
    return rows


_TIME_RE = re.compile(r"\d{1,2}:\d{2}\s*[AP]M|\d{3,4}\s*[AP]M|\d{1,2}\s*[AP]M", re.IGNORECASE)


def _recap_sentences(text: str) -> list[str]:
    """mancini.parser.split_sentences, but a sentence may end in a closing
    quote (``...at 7777." We recovered``) — his recap quotes his own letter,
    and the parser's split runs those two sentences together."""
    raw = re.split(r"""(?:(?<=[.!?])|(?<=[.!?]["'\u201c\u201d\u2019]))\s+(?=[A-Z"'\u201c])""", text)
    return [x.strip() for x in raw if len(x.strip()) > 15]


def _time_nearest(sentence: str, at: int) -> str | None:
    """The time mention nearest the setup word (``tweeted the long at 1:40PM:
    This was a ... Failed Breakdown`` names two times; the nearer is his)."""
    from mancini.parser import _normalize_time
    best, best_d = None, None
    for m in _TIME_RE.finditer(sentence):
        d = min(abs(m.start() - at), abs(m.end() - at))
        if best_d is None or d < best_d:
            best, best_d = m.group(0), d
    return _normalize_time(best) if best else None


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
    sibling within 30 min; LEVEL at his level but no time agreement; MISS.
    ``word_match`` (Addendum A4): on a matched row, whether his word for the
    setup is the machine's word; None on a MISS."""
    rank = {"EXACT": 3, "FAMILY": 2, "LEVEL": 1, "MISS": 0}
    confirmed = [c for c in calls if c.get("type") == "SetupRecognition"
                 and c.get("state") == "confirmed" and c.get("anchor") is not None]
    out: list[dict] = []
    for r in rows:
        best = {"tier": "MISS", "matched_ct": None, "matched_setup": None, "word_match": None}
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
                best = {"tier": tier, "matched_ct": c["ct"], "matched_setup": c.get("setup"),
                        "word_match": same}
        out.append(r | best)
    return out


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
            k = seg.pos_of(ev)
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
    """Spec §3d plus Addendum A1. Each flag names the bar it points at."""
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
        pk, rk = c.get("anchor_kind_parse"), c.get("anchor_kind")
        # Strader's rule (Addendum A1): the parse says resistance, the recognizer
        # said support. The parse also says trigger / target / pivot; those show
        # on the call row beside the anchor and do not trip the flag.
        if pk == "resistance" and rk is not None and pk != rk:
            out.append({"flag": "kind-mismatch", "anchor": c["anchor"], "bar": c["bar_i"],
                        "at": c["ct"], "parse_kind": pk, "recognizer_kind": rk,
                        "why": f"the parse calls {c['anchor']:g} {pk}; the recognizer "
                               f"confirmed a {c.get('setup') or 'setup'} on it as {rk}"})
    for l in legs:
        if l["tag"] == "silent" and l["near_level"]:
            out.append({"flag": "silent-move", "bar": l["origin_bar"], "at": l["origin_ct"],
                        "pts": l["pts"], "direction": l["direction"], "anchor": l["nearest_level"],
                        "why": f"{l['pts']:g} pts {l['direction']} from {l['origin_ct']} near "
                               f"{l['nearest_level']:g}, nothing said in the prior window"})
        if l["pts"] >= knobs.breakout_pts and l["near_level"] and l["tag"] != "called" and \
           l["said_before"] and all(" invalidated " in s for s in l["said_before"]):
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
                letter_status: str = "not-received",
                parsed_kinds: dict[float, str] | None = None) -> dict:
    """The whole day as one dict — the ``<day>.json`` of spec §4a.

    The runs are stitched first (see ``stitch``): a restart's re-walk of the
    tape is not measured twice, and a call late in one run is measured on
    into the next. ``res["runs"]`` still lists every run as the file has it,
    with the bars each re-walked. ``parsed_kinds`` is {price: kind} from the
    day's Mancini parse (Addendum A1).
    """
    day_seg = stitch(segments)
    calls: list[dict] = []
    legs: list[dict] = []
    cen = {"by_type": {}, "per_anchor": [], "n_calls_measured": 0}
    lo = hi = None
    if day_seg is not None and day_seg.bars:
        calls = measure_calls(day_seg, knobs, parsed_kinds)
        for row in calls:
            row["session"] = session_of(datetime.fromisoformat(row["t1"]))
        anchors = set(day_seg.mancini) | {float(e["price"]) for e in day_seg.events
                                          if e.get("type") == "Level" and e.get("price") is not None}
        legs = tag_legs(keep_legs(zigzag_legs(day_seg.bars, knobs.x_pts), knobs), day_seg,
                        anchors=sorted(anchors), knobs=knobs)
        for row in legs:
            k = day_seg.pos(row["origin_bar"], row["run"])
            row["session"] = session_of(day_seg.bars[k].t1) if k is not None else "?"
        cen = census(day_seg, calls)
        lo = min(b.l for b in day_seg.bars)
        hi = max(b.h for b in day_seg.bars)
    bars = day_seg.bars if day_seg is not None else []
    cash = [b for b in bars if session_of(b.t1) == "cash"]
    cash_range = (max(b.h for b in cash) - min(b.l for b in cash)) if cash else 0.0
    coverage = {
        "first_ct": bars[0].t0.strftime("%H:%M") if bars else None,
        "last_ct": bars[-1].t1.strftime("%H:%M") if bars else None,
        "bars": len(bars),
        "unmeasured_note": None,
    }
    if bars:
        last = bars[-1].t1
        if last.date() == now.date() and last < now - timedelta(minutes=30):
            coverage["unmeasured_note"] = (
                f"record ends {last.strftime('%H:%M')} CT; "
                f"{int((now - last).total_seconds() // 60)} minutes before the pass unmeasured")
    recap = {"status": letter_status, "rows": match_recap(recap_rows, calls) if recap_rows else []}
    overlap = (day_seg.meta.get("overlap_bars") or {}) if day_seg is not None else {}
    runs = []
    for s in segments:
        span = s.span
        runs.append({"run": s.run_no, "started": s.started, "bars": len(s.bars),
                     "complete": s.complete, "anchorless": s.anchorless,
                     "first_ct": span[0].strftime("%H:%M") if span else None,
                     "last_ct": span[1].strftime("%H:%M") if span else None,
                     "overlap_bars": int(overlap.get(s.run_no, 0))})
    return {
        "day": day.isoformat(), "source": source, "pass": pass_name,
        "generated_at": now.isoformat(),
        "bar_n": segments[0].bar_n if segments else None,
        "runs": runs,
        "anchors": sorted({a for s in segments for a in s.mancini}),
        "coverage": coverage,
        "range": {"low": lo, "high": hi, "cash": round(cash_range, 2)},
        "census": cen, "calls": calls, "legs": legs, "recap": recap,
        "flags": flags(calls, legs, cen, session_range=cash_range, knobs=knobs),
        "knobs": knobs_to_dict(knobs),
    }


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
    tmp = day_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    tmp.replace(day_path)
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
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("%s: unreadable line skipped", path.name)
                continue
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
        pk, rk = c.get("anchor_kind_parse"), c.get("anchor_kind")
        if pk is not None and rk is not None and pk != rk:
            what += f" (parse: {pk})"
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
    if c.get("lid_rejections") is not None or c.get("window_delta") is not None:
        wd = c.get("window_delta")
        cells.append(f"{_f(c.get('lid_rejections'))} / {wd:+d}" if wd is not None else _f(c.get("lid_rejections")))
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
    restarts = ""
    if len(runs) > 1:
        parts = []
        for r in runs[1:]:
            ov = r.get("overlap_bars") or 0
            parts.append(f"{r['started'][11:16]}" + (f" (re-walked {ov} bars, measured once)" if ov else ""))
        restarts = " — restarts at " + ", ".join(parts)
    L.append("")
    L.append(f"Record: {cov['first_ct'] or '?'} → {cov['last_ct'] or '?'} CT, {cov['bars']} bars of "
             f"{_f(res.get('bar_n'))} contracts; {len(runs)} run(s){restarts}. "
             f"Anchors in play: {len(res['anchors'])} Mancini levels.")
    for r in runs:
        if r.get("anchorless"):
            L += ["", f"**Run {r['run']} carried no Mancini levels** ({r.get('first_ct') or '?'} → "
                      f"{r.get('last_ct') or '?'} CT) — no calls there is not nothing to call."]
    if cov.get("unmeasured_note"):
        L += ["", f"**Note:** {cov['unmeasured_note']}."]
    if res.get("range", {}).get("cash"):
        L.append("")
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
    hdr += [f"±{_f(knobs.target_pts)} first", "Back to level", "Confirm lag", "Lid rej / window delta"]
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
          f"\"Near a level\" is within {_f(knobs.z_pts)} points; \"said before\" looks back {knobs.w_min} minutes. "
          f"\"Lid rejections\" counts bars in the {knobs.lid_window_min} minutes before the start whose high "
          f"came within {knobs.lid_ticks} ticks under the nearest level and closed under it (mirrored for down "
          f"legs); \"window delta\" is the buy-minus-sell volume over those same minutes, beside how far "
          f"price moved in them.",
          "", "| Start CT | End CT | Dir | Points | Minutes | Nearest level (dist) | Near | Lid rejections "
              "| Window delta / px change | Said before | Tag |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for l in res["legs"]:
        said = ", ".join(l["said_before"]) if l["said_before"] else "nothing"
        wd = l.get("window_delta")
        wpx = l.get("window_px_change")
        win = "—" if wd is None else f"{wd:+d} / {wpx:+.2f}"
        L.append(f"| {l['origin_ct']} | {l['end_ct']} | {l['direction']} | {_f(l['pts'])} | {l['minutes']} "
                 f"| {_f(l['nearest_level'])} ({_f(l['level_distance'])}) | {'yes' if l['near_level'] else 'no'} "
                 f"| {_f(l.get('lid_rejections'))} | {win} | {said} | **{l['tag']}** |")
    if not res["legs"]:
        L.append("| — | — | — | — | — | — | — | — | — | — | — |")
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
                     f"| {r.get('matched_ct') or '—'} {r.get('matched_setup') or ''} | "
                     f"{r['quote'][:160].replace('|', '/').replace(chr(10), ' ')} |")
        matched = [r for r in rc["rows"] if r.get("tier") != "MISS"]
        other = sum(1 for r in matched if r.get("word_match") is False)
        if matched:
            L += ["", f"{other} of {len(matched)} matched setups he named by the other word "
                      f"(his Failed Breakdown was the machine's level_reclaim, or the reverse)."]
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


# --------------------------------------------------------------- backfill

def _dist(vals: list) -> dict:
    if not vals:
        return {"n": 0, "median": None, "p10": None, "p90": None, "max": None}
    s = sorted(vals)

    def q(p: float):
        return s[min(len(s) - 1, int(p * (len(s) - 1)))]

    return {"n": len(s), "median": statistics.median(s), "p10": q(0.1), "p90": q(0.9), "max": s[-1]}


def _add_counts(into: dict, more: dict) -> None:
    for k, n in more.items():
        into[k] = into.get(k, 0) + n


def backfill_summary(day_rows: list[dict], knobs: Knobs) -> dict:
    """Distributions over the backfilled days (spec §6): calls per day, ±target
    outcomes by setup, legs per day at X and its two neighbours, silent-near-
    level legs per day, and (Addendum A3) confirmed outcomes split by lid
    rejections before the confirm."""
    ok = [r for r in day_rows if r.get("status") == "ok"]
    legs_at: dict[str, list[int]] = {}
    by_setup: dict[str, dict[str, int]] = {}
    by_lid: dict[str, dict[str, int]] = {"ge3": {}, "lt3": {}}
    for r in ok:
        for k, v in r.get("legs_at", {}).items():
            legs_at.setdefault(k, []).append(v)
        for s, v in r.get("by_setup", {}).items():
            _add_counts(by_setup.setdefault(s, {}), v)
        for s, v in r.get("by_lid", {}).items():
            _add_counts(by_lid.setdefault(s, {}), v)
    return {
        "n_days": len(ok), "skipped": [r for r in day_rows if r.get("status") != "ok"],
        "first": ok[0]["day"] if ok else None, "last": ok[-1]["day"] if ok else None,
        "confirmed_per_day": _dist([r["n_confirmed"] for r in ok]),
        "legs_per_day_at": {k: _dist(v) for k, v in sorted(legs_at.items(), key=lambda kv: float(kv[0]))},
        "silent_near_per_day": _dist([r["n_silent_near"] for r in ok]),
        "by_setup": by_setup,
        "by_lid": by_lid,
        "knobs": knobs_to_dict(knobs),
    }


def _outcome_row(label: str, v: dict) -> str:
    return (f"| {label} | {v.get('win', 0)} | {v.get('loss', 0)} | {v.get('neither', 0)} "
            f"| {v.get('both-in-one-bar', 0)} |")


def render_backfill_page(s: dict) -> str:
    k = s["knobs"]
    big = max(k["windows_min"])
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
          f"## ±{_f(float(k['target_pts']))} first touch by setup ({big} min)", "",
          "| Setup | win | loss | neither | both in one bar |", "|---|---|---|---|---|"]
    for setup, v in sorted(s["by_setup"].items()):
        L.append(_outcome_row(setup, v))
    L += ["", f"## ±{_f(float(k['target_pts']))} first touch by the lid before the confirm ({big} min)", "",
          f"Lid rejections: bars in the {k['lid_window_min']} minutes before the confirm bar whose high came "
          f"within {k['lid_ticks']} ticks under the anchor and closed under it.", "",
          "| Confirms with… | win | loss | neither | both in one bar |", "|---|---|---|---|---|",
          _outcome_row("3 or more lid rejections", s["by_lid"].get("ge3", {})),
          _outcome_row("fewer than 3", s["by_lid"].get("lt3", {}))]
    if s["skipped"]:
        L += ["", "## Skipped days", ""] + [f"- {r['day']}: {r.get('status')}" for r in s["skipped"]]
    L += ["", FOOTER, ""]
    return "\n".join(L)
