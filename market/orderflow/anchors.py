"""Day-anchor derivation — the one rule for what the recognizer watches. [st-055]

Both the drill surface (scripts/orderflow_drill.py) and the replay recorder
(market/orderflow/session_record.py) must run the recognizer against the SAME
anchor set, or the record Steve reviews will not match the surface he watched.
This module owns that rule: the day's Mancini levels (the validated anchor
source, st-3vu) as anchors OF THE KIND THE LETTER GAVE THEM — a support
engages on a flush below it, a resistance on a push above it [st-tme,
st-q5xu] — plus the session range edges so unlabeled days still surface
``range_trap`` recognitions.

Until 2026-08-19 every Mancini level entered as ``support``. On 2026-08-05,
with ES parabolic and the whole ladder overhead, the recognizer read a push
above 7815 (a resistance in the parse) that fell back beneath it as a bullish
``failed_breakdown forming`` — a failed BREAKOUT, the bear read, labelled as
the long. Same silhouette, opposite meaning, because the kind was dropped
(`knowledge/direction-inversion-watch.md`, one level down: verify the
anchor's role, then name the move).
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date
from pathlib import Path

from market.orderflow.recognizer import Anchor

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
LABELS = ROOT / "docs/measurement/mancini-setup-labels-2026-07-06.json"
PARSED = ROOT / "runbook/mancini/parsed"
FAMILY = {"failed_breakdown", "level_reclaim"}

# What a parsed Mancini level kind means to the recognizer. A ``pivot`` is a
# level price trades around — engaged from either side, so it is two anchors
# at one price. ``trigger`` and ``target`` are his commentary about a
# direction or a destination, not a ladder level: "bear case begins below
# 7695" says which way, not which side the level is on (the 08-19 letter's
# 7738 "reclaims are a possible long trigger" was yesterday's CEILING, and
# admitting it as support is what printed ``failed_breakdown @ 7738`` on a
# breakout retest). A level whose role we cannot read is not watched; the
# price still reaches the chart and the confluence set via
# ``mancini_levels_for``.
ANCHOR_KINDS_BY_PARSE_KIND: dict[str, tuple[str, ...]] = {
    "support": ("support",),
    "resistance": ("resistance",),
    "pivot": ("support", "resistance"),
    "trigger": (),
    "target": (),
}
Kinds = dict[float, tuple[str, ...]]     # price -> anchor kinds at that price


def _read_parse(day: _date) -> list[dict]:
    path = PARSED / f"{day.isoformat()}.json"
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("could not read Mancini parse for %s (%s)", day, e)
        return []
    return [x for x in doc.get("levels", [])
            if isinstance(x, dict) and x.get("price") is not None
            and 5000 < float(x["price"]) < 9000]


def parsed_mancini_levels(day: _date) -> list[float]:
    """The day's level PRICES from its own Mancini parse artifact. [st-b0n9]

    The labeled corpus (``LABELS``) stops at the hand-labeled study days, so
    every recent session — including today's, the one a live surface needs —
    resolves to no anchors at all, leaving the recognizer watching nothing but
    range edges. This reads the pre-open parse the runbook already writes.

    Every kind, prices only — this is the chart's level list and the
    confluence set. Which of them the recognizer WATCHES, and from which
    side, is ``parsed_mancini_kinds``.
    """
    return sorted({round(float(x["price"]), 2) for x in _read_parse(day)})


def parsed_mancini_kinds(day: _date) -> Kinds:
    """{price: anchor kinds} from the day's parse, per
    ``ANCHOR_KINDS_BY_PARSE_KIND``. A price the letter lists under more than
    one kind (a resistance that is also a target, a support that is also a
    trigger) carries the union. Every price in ``parsed_mancini_levels`` is a
    key; a price with an empty tuple is on the chart and not watched."""
    kinds: dict[float, set[str]] = {}
    for x in _read_parse(day):
        price = round(float(x["price"]), 2)
        k = str(x.get("kind") or "").lower()
        if k not in ANCHOR_KINDS_BY_PARSE_KIND:
            logger.warning("Mancini parse %s: unknown level kind %r at %g — not an anchor",
                           day, x.get("kind"), price)
        kinds.setdefault(price, set()).update(ANCHOR_KINDS_BY_PARSE_KIND.get(k, ()))
    return {p: tuple(k for k in ("support", "resistance") if k in ks)
            for p, ks in sorted(kinds.items())}


def mancini_levels_for(day: _date) -> list[float]:
    """The day's Mancini level prices — chart lines and the confluence set.

    The labeled corpus (score_recognizer.py's validated source, st-3vu) wins
    the SUPPORT side wherever it covers the day, so no labeled day's support
    anchors move — every prior run's bullish stream reproduces. A labeled day
    additionally gains the RESISTANCE prices from its own parse artifact where
    one exists [st-2a8v]: the labels are the supports of hand-labeled
    failed-breakdown / level-reclaim setups and are silent about the ladder
    overhead, so without the merge the 89 labeled tape days measure blind on
    the resistance side. Resistance anchors cannot emit a bullish setup, so
    the merge provably leaves the bullish stream unchanged (pinned by test).

    Days the labels do not cover fall back to that day's own parse — which is
    what makes a live session and a later replay of it watch the SAME anchor
    set instead of the live surface watching range edges alone. Empty when
    neither exists.

    Pair with ``mancini_kinds_for`` (same sources, same precedence) for the
    side each level is engaged from.
    """
    labeled = _labeled_levels(day)
    if labeled:
        res = [p for p, ks in parsed_mancini_kinds(day).items()
               if "resistance" in ks and p not in labeled]
        return sorted(set(labeled) | set(res))
    parsed = parsed_mancini_levels(day)
    if parsed:
        logger.info("Mancini anchors for %s: %d from the day's parse (unlabeled day)",
                    day, len(parsed))
    return parsed


def mancini_kinds_for(day: _date) -> Kinds:
    """{price: anchor kinds} for the day, same precedence as
    ``mancini_levels_for``: label prices are supports by construction, plus
    the parse's resistance side on labeled days [st-2a8v]; else the parse's
    own kinds. Every price ``mancini_levels_for`` returns is a key here."""
    labeled = _labeled_levels(day)
    if labeled:
        kinds: dict[float, set[str]] = {p: {"support"} for p in labeled}
        for p, ks in parsed_mancini_kinds(day).items():
            if "resistance" in ks:
                kinds.setdefault(p, set()).add("resistance")
        return {p: tuple(k for k in ("support", "resistance") if k in ks)
                for p, ks in sorted(kinds.items())}
    return parsed_mancini_kinds(day)


def mancini_source_for(day: _date) -> str:
    """Which source ``mancini_levels_for`` / ``mancini_kinds_for`` resolve the
    day to: ``"labels"`` (hand-labeled corpus), ``"letter"`` (the day's parse)
    or ``"none"``."""
    if _labeled_levels(day):
        return "labels"
    return "letter" if parsed_mancini_levels(day) else "none"


def levels_from_arg(spec: str) -> tuple[list[float], Kinds]:
    """The ``--mancini-levels`` override, shared by the drill, the recorder
    and the live feed so one grammar anchors all three: comma-separated
    ``PRICE`` or ``PRICE:KIND`` with KIND one of support / resistance /
    pivot (``7800,7815:resistance,7820:pivot``). A bare price is a support —
    the pre-08-19 meaning of the flag, kept so existing invocations anchor
    what they always did."""
    prices: list[float] = []
    kinds: dict[float, set[str]] = {}
    for tok in (t.strip() for t in spec.split(",")):
        if not tok:
            continue
        price_s, _, kind = tok.partition(":")
        price = round(float(price_s), 2)
        kind = (kind or "support").strip().lower()
        if kind not in ANCHOR_KINDS_BY_PARSE_KIND or not ANCHOR_KINDS_BY_PARSE_KIND[kind]:
            raise ValueError(f"--mancini-levels: {tok!r} — kind must be support, "
                             f"resistance or pivot")
        prices.append(price)
        kinds.setdefault(price, set()).update(ANCHOR_KINDS_BY_PARSE_KIND[kind])
    return (sorted(set(prices)),
            {p: tuple(k for k in ("support", "resistance") if k in ks)
             for p, ks in sorted(kinds.items())})


def kinds_to_records(kinds: Kinds | None) -> list[list] | None:
    """``Kinds`` as JSON-safe ``[[price, kind], ...]`` rows for a run log or
    page meta; ``kinds_from_records`` reads them back. None stays None (an
    older log with no kinds row replays as all-supports, which is what it
    ran)."""
    if kinds is None:
        return None
    return [[p, k] for p, ks in sorted(kinds.items()) for k in ks]


def kinds_from_records(rows) -> Kinds | None:
    if rows is None:
        return None
    out: dict[float, list[str]] = {}
    for p, k in rows:
        out.setdefault(round(float(p), 2), []).append(str(k))
    return {p: tuple(ks) for p, ks in out.items()}


def _labeled_levels(day: _date) -> list[float]:
    if not LABELS.exists():
        return []
    try:
        entries = json.loads(LABELS.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("could not read Mancini labels (%s); using range edges only", e)
        return []
    lv = {round(float(x), 2)
          for e in entries
          if e.get("session_date") == day.isoformat() and e.get("setup") in FAMILY
          for x in e.get("es_levels", []) if 5000 < float(x) < 9000}
    return sorted(lv)


def _kinds_of(price: float, kinds: Kinds | None) -> tuple[str, ...]:
    """Anchor kinds for one Mancini price. ``kinds is None`` is the legacy /
    test default — every level a support. With a kinds map, a price it does
    not name is a level we could not read the role of: on the chart, not
    watched."""
    if kinds is None:
        return ("support",)
    return kinds.get(round(price, 2), ())


def day_anchors(mancini_levels: list[float], session_high: float,
                session_low: float, kinds: Kinds | None = None) -> list[Anchor]:
    """Mancini levels as anchors of their parsed kind (``kinds``, from
    ``mancini_kinds_for``; None = every level a support) plus the session
    range edges, deduped on (price, kind)."""
    anchors: list[Anchor] = []
    seen: set[tuple[float, str]] = set()

    def add(price: float, kind: str, label: str, mancini: bool = False) -> None:
        key = (round(price, 2), kind)
        if key in seen:
            return
        seen.add(key)
        anchors.append(Anchor(price, kind, label, mancini=mancini))

    for lv in mancini_levels:
        for kind in _kinds_of(lv, kinds):
            add(lv, kind, f"mancini {lv:g}", mancini=True)
    add(session_high, "range_high", "day high")
    add(session_low, "range_low", "day low")
    return anchors


class LiveAnchors:
    """``day_anchors`` for a session that has not happened yet. [st-b0n9]

    THE PROBLEM: ``day_anchors`` takes the session high and low, which a replay
    knows on bar 0 and a live session does not. That is lookahead the drill
    surface gets for free and the live surface cannot have — there is no way to
    make the two agree in real time, so the question is which divergence to
    take.

    THE RULE: Mancini levels are fixed (they come from the pre-open parse, so
    live and replay hold the identical set). The two range edges START at the
    first bar's high and low and EXTEND with the developing session. They
    converge on the replay's values as the day completes, so live and the
    replay record end the session watching the same anchor set; they differ
    only in that live could not react to an extreme before it printed. Seeding
    from the prior session instead would diverge permanently.

    WHY THE IDLE GUARD: a range edge is, by definition, broken exactly when a
    new extreme prints — the same bar that would extend it. Extending an anchor
    while an engagement is measuring against its price rewrites the level
    mid-read, and no range_trap could ever complete. So an edge is frozen the
    moment it engages and resumes extending once the recognizer says it is idle
    again.

    ``Anchor`` is frozen, so moving an edge is a SWAP. Engagement state is
    keyed on ``id(anchor)``, which is why the swap goes through
    ``SetupRecognizer.retarget`` rather than happening here: the recognizer
    owns that state and refuses the move when the anchor is not idle. Without a
    recognizer (tests, or a set nobody is judging against) the edges move
    freely — there is no state to protect.
    """

    def __init__(self, mancini_levels: list[float], session_open=None,
                 kinds: Kinds | None = None):
        """``kinds``: the Mancini levels' anchor kinds (``mancini_kinds_for``);
        None = every level a support. The live feed and the parity replay
        of its run log must pass the same map, or the two watch different
        anchor sets — the run log carries it for that reason.

        ``session_open`` (tz-aware datetime, optional): bars that START
        before it do not seed or extend the range edges [st-fgno]. The tape
        starts at 02:50 CT (st-btu) and without this the "day high/low" the
        recognizer judges against were the overnight range from the first
        bar of the tape. Steve, 2026-08-18: session means the cash session.
        None keeps the seed-from-first-bar behaviour (tests, replays of a
        tape that is itself RTH-only)."""
        self.session_open = session_open
        self.mancini = sorted(float(x) for x in mancini_levels)
        self.kinds = kinds
        # Placeholder edges; the first bar seeds them before anything is judged.
        self.anchors = day_anchors(self.mancini, 0.0, 0.0, kinds)
        self._hi = next(i for i, a in enumerate(self.anchors) if a.kind == "range_high")
        self._lo = next(i for i, a in enumerate(self.anchors) if a.kind == "range_low")
        self._rec = None
        self._seeded = False

    def attach(self, recognizer) -> "LiveAnchors":
        """Bind to the recognizer that judges against these anchors.

        ``SetupRecognizer`` copies the list it is given, so without this there
        would be TWO lists holding the same anchors and every swap would have
        to update both in step — a sync invariant nobody would remember. Point
        at the recognizer's list instead and there is only one.
        """
        self._rec = recognizer
        self.anchors = recognizer.anchors
        return self

    @property
    def high(self) -> Anchor:
        return self.anchors[self._hi]

    @property
    def low(self) -> Anchor:
        return self.anchors[self._lo]

    def _move(self, slot: int, price: float) -> None:
        old = self.anchors[slot]
        if self._rec is None:
            self.anchors[slot] = Anchor(price, old.kind, old.label, old.mancini)
        else:
            self._rec.retarget(old, price)   # no-op when engaged; shared list

    def observe(self, bar) -> None:
        """Extend the developing range edges from a completed bar.

        Call BEFORE handing the bar to the recognizer, so the bar is judged
        against the session it belongs to. A bar that starts before
        ``session_open`` is pre-open tape: it is judged (against the Mancini
        levels and the placeholder edges) but never becomes the day's range.
        """
        if self.session_open is not None:
            start = getattr(bar, "start_ts", None)
            if start is not None and start < self.session_open:
                return
        if not self._seeded:
            self._move(self._hi, bar.high)
            self._move(self._lo, bar.low)
            self._seeded = True
            return
        if bar.high > self.high.price:
            self._move(self._hi, bar.high)
        if bar.low < self.low.price:
            self._move(self._lo, bar.low)
