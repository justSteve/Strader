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
        k = seg.pos(ev.get("bar_i"))
        if k is None:
            continue
        direction = direction_of(ev)
        if direction not in ("bullish", "bearish"):
            continue
        bar = seg.bars[k]
        entry = float(ev.get("start_price", bar.c)) if ev["type"] == "SweepPrint" else bar.c
        anchor = float(ev["anchor_price"]) if ev.get("anchor_price") is not None else None
        row = {
            "run": seg.run_no, "bar_i": bar.i, "ct": bar.t1.strftime("%H:%M"),
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
        row = {
            "run": seg.run_no, "direction": leg.direction,
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
        if pk is not None and rk is not None and pk != rk:
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
                letter_status: str = "not-received",
                parsed_kinds: dict[float, str] | None = None) -> dict:
    """The whole day as one dict — the ``<day>.json`` of spec §4a.
    ``parsed_kinds`` is {price: kind} from the day's Mancini parse (Addendum A1)."""
    calls: list[dict] = []
    legs: list[dict] = []
    cens: list[dict] = []
    lo = hi = None
    for seg in segments:
        c = measure_calls(seg, knobs, parsed_kinds)
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
    runs = []
    for s in segments:
        span = s.span
        runs.append({"run": s.run_no, "started": s.started, "bars": len(s.bars),
                     "complete": s.complete, "anchorless": s.anchorless,
                     "first_ct": span[0].strftime("%H:%M") if span else None,
                     "last_ct": span[1].strftime("%H:%M") if span else None})
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
