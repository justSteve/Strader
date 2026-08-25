#!/usr/bin/env python3
"""Deterministic tape-event detection — the accuracy tier of the two-tier
emitter. [st-dgwj, st-85dv]

WHY THIS EXISTS. The 2026-08-24 audit of two emitter sessions found that
numerical accuracy in the narration came from the SCORER, not the model: both
models transcribed tool output near-perfectly and erred only where they were
recalling or characterising rather than reading. The failures were of the same
shape every time — an alert-grade bar went unremarked, or a superlative was
recalled instead of checked:

  - 2026-08-24 10:41-42, two consecutive absorption bars (d-122 / d-493, both
    net 0.00) — a thesis event, never narrated.
  - 2026-08-24 10:20, d-725 — a climax, never narrated.
  - 2026-08-24 13:14, "biggest buy-delta of the day" (+549), contradicting the
    same session's own 10:47 note of +786. Recalled, not grepped.
  - 2026-08-25 08:43, d-676 — the day's new max SELL delta — described as
    "both tests bought, net positive delta."

The fix is not a better prompt. It is to detect these mechanically and emit
them, so that noticing is a property of the instrument rather than of model
attention, and so a monitor can wake on an EVENT rather than on a clock.

WHAT THIS MODULE IS NOT. It does not grade, does not touch delta math, and
does not decide what an event MEANS. It reads the atom and the developing
grade the scorer already computed and says "this crossed a stated line." The
naming of setups and the stating of playbook implications belong to the analyst
tier under Steve's 2026-08-25 ruling (st-eaa8), on top of what is detected here.

THE FOUR CLASSES, and the measurement behind each threshold. Every default
below was set by measuring the real logs, not by taste:

  SUPERLATIVE       a new session max volume, max BUY delta, or max SELL delta.
                    Buy and sell are tracked SEPARATELY and deliberately. The
                    scorer's existing `smax` field ranks delta on |d|, so the
                    running maximum is whichever side happens to be larger and
                    the other side is simply invisible — which is exactly how
                    "biggest buy-delta of the day" got answered wrong from a
                    line that only ever showed a sell maximum.

  ABSORPTION-CLUSTER  >= `absorption_min_bars` consecutive bars with
                    effort_pct >= 85 and effect_pct <= 10. Measured against the
                    calibration case (2026-08-24 10:41-42): effort 85 and 90,
                    effect 6 and 6 — both inside the band, while the bars either
                    side (10:40 effect 94, 10:43 effect 57) are well outside it.
                    min_bars=2 is load-bearing: 2026-08-25 08:47 is a lone bar at
                    effort 97 / effect 7 and must NOT fire, because one bar of
                    absorption is a bar, not a cluster.

  CLIMAX            |delta| at or above the `climax_delta_pctl` mid-rank
                    percentile of the session's |delta| so far. Measured: on
                    2026-08-24, 10:20's d-725 sits at 99.8 and 08:42's d-1100 at
                    99.9, while 10:42's d-493 — large, but part of the absorption
                    cluster rather than a climax — sits at 99.0. A threshold of
                    99.5 therefore separates them cleanly. An absolute floor
                    guards the small-n start of a session, where a percentile is
                    cheap; mid-rank ranking helps here too, since it cannot reach
                    99.5 until roughly a hundred atoms are in.

  PLAN-LEVEL        touch, acceptance (`level_acceptance_closes` consecutive
                    closes through, having come from the other side), or
                    rejection at a loaded Mancini anchor. This is the class that
                    would have caught 2026-08-25's "upper edge 7699.75 unbroken"
                    written one sentence away from "bracketed to 7701", after
                    7701.25 had already printed.

EMISSION IS ADDITIVE. Every event renders as its own line, keyed `EVENT`, with
a machine-parsable `key=value` payload. Nothing here alters the graded or
partial lines the scorer already prints — a deploy of this must leave the
pre-existing minutes byte-identical, which is a stated acceptance condition of
the mid-session cutover and is asserted by the tests.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "tape_events.yaml"

KIND_SUPERLATIVE = "SUPERLATIVE"
KIND_ABSORPTION = "ABSORPTION-CLUSTER"
KIND_CLIMAX = "CLIMAX"
KIND_PLAN_LEVEL = "PLAN-LEVEL"

EVENT_MARK = "EVENT"          # the greppable token; a monitor filters on this

# RTH open in CENTRAL time, deliberately — atom timestamps are CT tape time, so
# comparing against a CT constant is DST-safe. A UTC constant here would be the
# same landmine already flagged against the context strip's hardcoded 13:30 UTC,
# which fires on the November changeover.
RTH_OPEN_CT = (8, 30)


def rth_minutes(ts: datetime) -> int:
    """Minutes since the RTH open, negative before it.

    Carried on SUPERLATIVE events because Steve's 2026-08-25 amendment makes the
    discount explicit: "within-day superlatives early in RTH are additionally
    discounted — sixty minutes in, some bar is always the record." That is
    mechanically knowable, and st-eaa8's mechanical-first condition says anything
    mechanically knowable belongs here rather than in the analyst's memory.

    The calibration case is exactly 60: 2026-08-25 09:30 set BOTH the day's max
    volume (14,778) and max sell delta (-1240) on one 17-point bar, met every
    mechanical failed-breakdown criterion on the reclaim, and returned about 3.75
    points inside a roughly 12-point rotation. The detection was right; treating
    it as an entry was not.
    """
    open_min = RTH_OPEN_CT[0] * 60 + RTH_OPEN_CT[1]
    return (ts.hour * 60 + ts.minute) - open_min


@dataclass(frozen=True)
class EventKnobs:
    """Every threshold that decides whether a bar is worth waking a model for.
    Steve owns the numbers (config/tape_events.yaml); the defaults here are the
    measured ones described in the module docstring."""
    # 80, not 85, and the three points of difference are the whole lesson. The
    # calibration cluster (2026-08-24 10:41-42) READS as effort 85 and 90 in the
    # log, because the graded line prints percentiles with ".0f". The true values
    # are 84.7 and 90.4. A threshold of 85.0 calibrated from the printed line
    # therefore missed the exact case this class was built for, by 0.3, while a
    # unit test written from those same printed numbers passed. Thresholds are
    # set against the underlying floats now, with room for the next such bar.
    # The selective condition here is the effect one anyway: a bar at the 6th
    # percentile of displacement is doing nothing with real volume behind it.
    absorption_effort_pct: float = 80.0
    absorption_effect_pct: float = 10.0
    absorption_min_bars: int = 2

    climax_delta_pctl: float = 99.5
    climax_min_abs_delta: int = 300
    climax_min_atoms: int = 60

    # A "day max" called in the first minutes of a session is arithmetic, not
    # news: with three atoms in, every one of them sets some record.
    superlative_min_atoms: int = 30
    superlative_min_vol: int = 500
    superlative_min_abs_delta: int = 150

    # PLAN-LEVEL needs hysteresis, and the reason is measured. The anchor set is
    # not a handful of plan levels: 2026-08-24 loaded 69 of them, a grid roughly
    # every 5-10 points across a 600-point span. A naive touch/accept/reject
    # detector over that grid fired 415 times in one session — level 7674 alone
    # announced acceptance 58 times as price chopped across it. Every knob below
    # exists to make an event mean "price did something decisive here" rather
    # than "price wobbled near a number".
    level_acceptance_closes: int = 2
    # A close must be this far THROUGH the anchor to count toward acceptance,
    # so a one-tick straddle is not a decision.
    level_acceptance_min_pts: float = 1.0
    # A rejection must actually poke through before failing — an extreme that
    # merely touches the level is a touch, not a rejection.
    level_penetration_min_pts: float = 0.5
    level_rejection_min_pts: float = 0.75
    # Acceptance re-arms only after a decisive move to the OTHER side, not on
    # any crossing; otherwise every oscillation re-announces the same fact.
    level_reset_pts: float = 2.0
    # One event of a given kind per level per this many minutes. Chop around an
    # anchor is one situation, not forty.
    level_event_cooldown_min: int = 20
    # Anchors far from where price is trading cannot be touched this minute and
    # only cost time; this bounds the per-atom level scan.
    level_max_distance_pts: float = 25.0
    # HOW MANY ANCHORS COUNT AS "IN PLAY", per side. mancini_levels_for returns
    # the whole ladder — 69 prices spanning 7517-8079 on 2026-08-24, a grid every
    # 5-10 points — not the handful of levels a plan is actually about. Watching
    # all of them inside a distance band still produced 163 level events in a
    # session, which is noise wearing an event's clothes.
    #
    # Which levels MATTER is a trading judgement and not this module's to make.
    # So the scope is mechanical instead: the nearest anchor above and the
    # nearest below are the bracket price is currently trading inside, and an
    # event on one of those is by construction about the structure in play. That
    # is also exactly the shape of the failure this class exists for — 2026-08-25
    # narrated "upper edge 7699.75 unbroken" one sentence from "bracketed to
    # 7701", after 7701.25 had printed. Raise this knob to widen the ladder.
    level_scan_nearest: int = 1


def knobs_to_dict(k: EventKnobs) -> dict:
    return {f: getattr(k, f) for f in k.__dataclass_fields__}


def load_knobs(path: Path | None = None) -> EventKnobs:
    """Read config/tape_events.yaml over the defaults. A missing file is normal
    and means "use the measured defaults"; an unknown key is a loud failure
    rather than a silent no-op, because a typo'd threshold that quietly does
    nothing is the worst outcome for a knob whose whole job is to be tuned."""
    p = path or CONFIG_PATH
    if not p.exists():
        return EventKnobs()
    import yaml
    doc = yaml.safe_load(p.read_text()) or {}
    known = set(EventKnobs.__dataclass_fields__)
    unknown = set(doc) - known
    if unknown:
        raise ValueError(f"{p}: unknown tape-event knob(s): {sorted(unknown)}")
    return replace(EventKnobs(), **doc)


SIG_ALERT = "alert"
SIG_NOTE = "note"


@dataclass(frozen=True)
class TapeEvent:
    """One detected event. `fields` is ordered and rendered as key=value so the
    line is greppable by a human and parsable by awk or json-free tooling.

    `sig` SEPARATES DETECTION FROM WAKING, and that separation is the whole
    reason the numbers work. The anchor ladder is dense — 69 prices every 5-10
    points — so a trending session legitimately accepts through level after
    level, and a faithful detector emits 160+ level events in a day. None of
    them are wrong. But waking an expensive model 160 times is precisely the
    cost the two-tier design exists to avoid, and moving the judgement into the
    watcher's grep would put an untested policy in bash.

    So every event is emitted (the log stays complete and greppable, and the
    postmortem gets the full record), and each carries `sig`:

        alert — worth waking the analyst for, now
        note  — true, logged, and context when something else wakes it

    The monitor filters on `sig=alert`. Anything downstream wanting everything
    still has everything.
    """
    ts: datetime
    kind: str
    subtype: str
    fields: tuple[tuple[str, str], ...] = ()
    sig: str = SIG_ALERT

    @property
    def is_alert(self) -> bool:
        return self.sig == SIG_ALERT

    def line(self) -> str:
        payload = "  ".join(f"{k}={v}" for k, v in self.fields)
        return (f"{self.ts:%H:%M} CT  {EVENT_MARK} {self.kind} {self.subtype}  "
                f"sig={self.sig}  {payload}").rstrip()


def _fmt_px(x: float) -> str:
    return f"{x:g}"


def _midrank_pctl(sorted_vals: list[int], x: int) -> float:
    """Percentile of x within sorted_vals by MID-RANK — the same convention
    moves.grade_atoms_developing uses, and for the same reason: a lone
    observation must rank at 50 (with one sample you cannot know whether it is
    high or low), not at 100 by construction."""
    if not sorted_vals:
        return 50.0
    lo = bisect.bisect_left(sorted_vals, x)
    hi = bisect.bisect_right(sorted_vals, x)
    return 100.0 * (lo + hi) / 2.0 / len(sorted_vals)


@dataclass
class _LevelState:
    """Per-anchor crossing state. `side` is where the last close sat relative to
    the level; `run` counts consecutive closes on that side.

    `seen_a_crossing` is what stops every level price merely sits above from
    announcing acceptance on its second bar. Acceptance means price traded
    THROUGH an anchor and stayed there; a level that has only ever been on one
    side has not been accepted through, it has just been distant."""
    side: str | None = None        # "above" | "below" | None
    run: int = 0
    spanned_last_bar: bool = False
    announced_acceptance_side: str | None = None
    seen_a_crossing: bool = False
    last_event: dict = field(default_factory=dict)   # subtype -> ts of last emit
    alerted: set = field(default_factory=set)        # subtypes already alerted on


@dataclass
class _Cluster:
    bars: list = field(default_factory=list)   # (ts, effort, effect, vol, delta)

    def reset(self):
        self.bars = []


class TapeEventDetector:
    """Fed one graded atom at a time, in order, returns the events it triggers.

    Causal by construction: every decision uses only atoms already seen, so a
    replay over a finished tape produces exactly the events a live session would
    have produced at the same minute. That property is what lets the mid-session
    cutover be verified — the morning replays identically — and what lets the
    Bead-6 rubric score a day after the fact against what was actually knowable
    at the time.
    """

    def __init__(self, *, levels: list[float] | None = None,
                 kinds: dict[float, tuple[str, ...]] | None = None,
                 knobs: EventKnobs | None = None):
        self.levels = sorted(levels or [])
        self.kinds = kinds or {}
        self.k = knobs or EventKnobs()

        self._abs_deltas: list[int] = []
        self._n = 0
        self._max_vol: tuple[int, datetime] | None = None
        self._max_buy: tuple[int, datetime] | None = None
        self._max_sell: tuple[int, datetime] | None = None
        self._cluster = _Cluster()
        self._levels_state: dict[float, _LevelState] = {}

    # ---------------------------------------------------------------- api ---
    def on_atom(self, atom, dev: dict) -> list[TapeEvent]:
        """`atom` is a moves.Atom; `dev` is the dict from
        grade_atoms_developing for that same atom. Neither is mutated."""
        self._n += 1
        events: list[TapeEvent] = []

        superlatives = self._superlatives(atom)
        events.extend(superlatives)
        # A new delta record is already a climax by any reading; saying both in
        # the same minute is noise, and the superlative is the stronger claim.
        delta_record = any(e.subtype in ("MAX-BUY-DELTA", "MAX-SELL-DELTA")
                           for e in superlatives)
        events.extend(self._climax(atom, suppressed=delta_record))
        events.extend(self._absorption(atom, dev))
        events.extend(self._plan_levels(atom))

        bisect.insort(self._abs_deltas, abs(atom.delta))
        return events

    # -------------------------------------------------------- superlatives ---
    def _superlatives(self, atom) -> list[TapeEvent]:
        out = []
        ripe = self._n >= self.k.superlative_min_atoms

        if self._max_vol is None or atom.volume > self._max_vol[0]:
            prev = self._max_vol
            self._max_vol = (atom.volume, atom.ts)
            if ripe and atom.volume >= self.k.superlative_min_vol:
                out.append(TapeEvent(atom.ts, KIND_SUPERLATIVE, "MAX-VOL", (
                    ("vol", str(atom.volume)),
                    ("prev", f"{prev[0]}@{prev[1]:%H:%M}" if prev else "none"),
                    ("delta", f"{atom.delta:+d}"),
                    ("net", f"{atom.net:+.2f}"),
                    ("close", _fmt_px(atom.close)),
                    ("rth_min", str(rth_minutes(atom.ts))),
                )))

        # Buy and sell maxima are separate series on purpose — see the module
        # docstring. Zero delta sets neither.
        if atom.delta > 0 and (self._max_buy is None or atom.delta > self._max_buy[0]):
            prev = self._max_buy
            self._max_buy = (atom.delta, atom.ts)
            if ripe and atom.delta >= self.k.superlative_min_abs_delta:
                out.append(TapeEvent(atom.ts, KIND_SUPERLATIVE, "MAX-BUY-DELTA", (
                    ("delta", f"{atom.delta:+d}"),
                    ("prev", f"{prev[0]:+d}@{prev[1]:%H:%M}" if prev else "none"),
                    ("vol", str(atom.volume)),
                    ("net", f"{atom.net:+.2f}"),
                    ("close", _fmt_px(atom.close)),
                    ("rth_min", str(rth_minutes(atom.ts))),
                )))
        if atom.delta < 0 and (self._max_sell is None or atom.delta < self._max_sell[0]):
            prev = self._max_sell
            self._max_sell = (atom.delta, atom.ts)
            if ripe and abs(atom.delta) >= self.k.superlative_min_abs_delta:
                out.append(TapeEvent(atom.ts, KIND_SUPERLATIVE, "MAX-SELL-DELTA", (
                    ("delta", f"{atom.delta:+d}"),
                    ("prev", f"{prev[0]:+d}@{prev[1]:%H:%M}" if prev else "none"),
                    ("vol", str(atom.volume)),
                    ("net", f"{atom.net:+.2f}"),
                    ("close", _fmt_px(atom.close)),
                    ("rth_min", str(rth_minutes(atom.ts))),
                )))
        return out

    def session_max(self) -> dict:
        """The running maxima, so a caller can answer a superlative question by
        READING rather than recalling — the whole point of st-6s6x's
        grep-not-recall rule."""
        def pack(t):
            return None if t is None else {"value": t[0], "ts": t[1]}
        return {"max_vol": pack(self._max_vol),
                "max_buy_delta": pack(self._max_buy),
                "max_sell_delta": pack(self._max_sell)}

    # -------------------------------------------------------------- climax ---
    def _climax(self, atom, *, suppressed: bool) -> list[TapeEvent]:
        if suppressed:
            return []
        if self._n < self.k.climax_min_atoms:
            return []
        if abs(atom.delta) < self.k.climax_min_abs_delta:
            return []
        # Rank against the session so far, EXCLUDING this atom — it is inserted
        # by on_atom after detection, so the percentile answers "how does this
        # compare with what came before", which is the causal question.
        pctl = _midrank_pctl(self._abs_deltas, abs(atom.delta))
        if pctl < self.k.climax_delta_pctl:
            return []
        return [TapeEvent(atom.ts, KIND_CLIMAX,
                          "SELL" if atom.delta < 0 else "BUY", (
                              ("delta", f"{atom.delta:+d}"),
                              ("pctl", f"{pctl:.1f}"),
                              ("vol", str(atom.volume)),
                              ("net", f"{atom.net:+.2f}"),
                              ("rng", f"{atom.range_pts:.2f}"),
                              ("close", _fmt_px(atom.close)),
                          ))]

    # ---------------------------------------------------------- absorption ---
    def _absorption(self, atom, dev: dict) -> list[TapeEvent]:
        effort = float(dev["effort_pct_dev"])
        effect = float(dev["effect_pct_dev"])
        in_band = (effort >= self.k.absorption_effort_pct
                   and effect <= self.k.absorption_effect_pct)

        out = []
        if in_band:
            self._cluster.bars.append(
                (atom.ts, effort, effect, atom.volume, atom.delta))
            if len(self._cluster.bars) == self.k.absorption_min_bars:
                out.append(self._cluster_event("START"))
            return out

        # Band broken: if a cluster had been announced, close it out so the
        # analyst learns the absorption resolved and how big it got.
        if len(self._cluster.bars) >= self.k.absorption_min_bars:
            out.append(self._cluster_event("END", broken_by=atom))
        self._cluster.reset()
        return out

    def _cluster_event(self, subtype: str, broken_by=None) -> TapeEvent:
        bars = self._cluster.bars
        vol = sum(b[3] for b in bars)
        delta = sum(b[4] for b in bars)
        fields = [
            ("bars", str(len(bars))),
            ("from", f"{bars[0][0]:%H:%M}"),
            ("to", f"{bars[-1][0]:%H:%M}"),
            ("vol", str(vol)),
            ("delta", f"{delta:+d}"),
            ("effort_pct", f"{min(b[1] for b in bars):.0f}+"),
            ("effect_pct", f"{max(b[2] for b in bars):.0f}-"),
        ]
        ts = bars[-1][0]
        if broken_by is not None:
            fields.append(("broken_by", f"{broken_by.ts:%H:%M}"))
            fields.append(("break_net", f"{broken_by.net:+.2f}"))
            ts = broken_by.ts
        # START is the alarm; END is the resolution, useful to read but not
        # worth a wake of its own.
        return TapeEvent(ts, KIND_ABSORPTION, subtype, tuple(fields),
                         sig=SIG_ALERT if subtype == "START" else SIG_NOTE)

    # --------------------------------------------------------- plan levels ---
    def _in_play(self, atom) -> list[float]:
        """The anchors bracketing this bar: the nearest `level_scan_nearest`
        at or above it and the same number at or below, subject to the distance
        bound. A level the bar actually spans is in play regardless of rank —
        price is standing on it."""
        n = max(1, self.k.level_scan_nearest)
        near = [lvl for lvl in self.levels
                if min(abs(atom.close - lvl), abs(atom.high - lvl),
                       abs(atom.low - lvl)) <= self.k.level_max_distance_pts]
        above = [lvl for lvl in near if lvl >= atom.close][:n]
        below = [lvl for lvl in reversed([lvl for lvl in near if lvl < atom.close])][:n]
        spanned = [lvl for lvl in near if atom.low <= lvl <= atom.high]
        return sorted(set(above) | set(below) | set(spanned))

    def _plan_levels(self, atom) -> list[TapeEvent]:
        out = []
        for lvl in self._in_play(atom):
            st = self._levels_state.setdefault(lvl, _LevelState())
            out.extend(self._level_events(atom, lvl, st))
        return out

    def _off_cooldown(self, st: _LevelState, subtype: str, ts: datetime) -> bool:
        """True if this level may announce `subtype` now. Records the emission,
        so call it only when actually emitting."""
        last = st.last_event.get(subtype)
        if last is not None:
            if (ts - last).total_seconds() < self.k.level_event_cooldown_min * 60:
                return False
        st.last_event[subtype] = ts
        return True

    @staticmethod
    def _level_sig(st: _LevelState, subtype: str) -> str:
        """The FIRST time a level is accepted through or rejects, that is news.
        The fifth time the same level does the same thing in a chopping session
        is the same fact restated, so it is logged as a note instead. This is
        what keeps a dense ladder from spending the whole wake budget."""
        if subtype in st.alerted:
            return SIG_NOTE
        st.alerted.add(subtype)
        return SIG_ALERT

    def _level_events(self, atom, lvl: float, st: _LevelState) -> list[TapeEvent]:
        out = []
        spans = atom.low <= lvl <= atom.high
        prior_side = st.side
        if atom.close > lvl:
            side = "above"
        elif atom.close < lvl:
            side = "below"
        else:
            side = prior_side  # a close exactly on the level decides nothing

        kind = (self.kinds.get(lvl) or ("",))[0]
        base = [("level", _fmt_px(lvl))]
        if kind:
            base.append(("anchor", kind))

        # How far this bar actually traded THROUGH the anchor, measured from the
        # side price approached from. A bar whose extreme merely reaches the
        # level has penetrated nothing.
        if prior_side == "above":
            penetration = max(0.0, lvl - atom.low)
        elif prior_side == "below":
            penetration = max(0.0, atom.high - lvl)
        else:
            penetration = 0.0

        # A rejection is a touch that failed, so it is reported instead of the
        # touch rather than alongside it — two lines for one bar at one level
        # would read as two events.
        rejected = (spans and prior_side is not None and side == prior_side
                    and penetration >= self.k.level_penetration_min_pts
                    and abs(atom.close - lvl) >= self.k.level_rejection_min_pts)
        if rejected:
            if self._off_cooldown(st, "REJECTION", atom.ts):
                out.append(TapeEvent(atom.ts, KIND_PLAN_LEVEL, "REJECTION", tuple(
                    base + [("from", prior_side),
                            ("close", _fmt_px(atom.close)),
                            ("extreme", _fmt_px(atom.low if prior_side == "above" else atom.high)),
                            ("through", f"{penetration:.2f}"),
                            ("back", f"{abs(atom.close - lvl):.2f}"),
                            ("vol", str(atom.volume)),
                            ("delta", f"{atom.delta:+d}")]),
                    sig=self._level_sig(st, "REJECTION")))
        elif spans and not st.spanned_last_bar:
            if self._off_cooldown(st, "TOUCH", atom.ts):
                out.append(TapeEvent(atom.ts, KIND_PLAN_LEVEL, "TOUCH", tuple(
                    base + [("close", _fmt_px(atom.close)),
                            ("high", _fmt_px(atom.high)),
                            ("low", _fmt_px(atom.low)),
                            ("vol", str(atom.volume)),
                            ("delta", f"{atom.delta:+d}")]),
                    sig=SIG_NOTE))

        if side != prior_side:
            st.run = 1
            if prior_side is not None:
                st.seen_a_crossing = True
        else:
            st.run += 1
        st.side = side
        st.spanned_last_bar = spans

        beyond = abs(atom.close - lvl)

        # Re-arm BEFORE considering a new announcement: acceptance of a side is
        # only news again once price has decisively left for the other one.
        # Clearing on any crossing instead is what let a level announce
        # acceptance 58 times in a session as price chopped across it.
        if st.announced_acceptance_side is not None:
            opposite = "below" if st.announced_acceptance_side == "above" else "above"
            if side == opposite and beyond >= self.k.level_reset_pts:
                st.announced_acceptance_side = None

        if (side is not None and st.seen_a_crossing and not rejected
                and st.run >= self.k.level_acceptance_closes
                and beyond >= self.k.level_acceptance_min_pts
                and st.announced_acceptance_side != side
                and self._off_cooldown(st, "ACCEPTANCE", atom.ts)):
            st.announced_acceptance_side = side
            out.append(TapeEvent(atom.ts, KIND_PLAN_LEVEL, "ACCEPTANCE", tuple(
                base + [("side", side),
                        ("closes", str(st.run)),
                        ("close", _fmt_px(atom.close)),
                        ("through", f"{beyond:.2f}"),
                        ("vol", str(atom.volume)),
                        ("delta", f"{atom.delta:+d}")]),
                sig=self._level_sig(st, "ACCEPTANCE")))
        return out
