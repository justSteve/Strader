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
