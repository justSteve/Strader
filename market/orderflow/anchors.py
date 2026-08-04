"""Day-anchor derivation — the one rule for what the recognizer watches. [st-055]

Both the drill surface (scripts/orderflow_drill.py) and the replay recorder
(market/orderflow/session_record.py) must run the recognizer against the SAME
anchor set, or the record Steve reviews will not match the surface he watched.
This module owns that rule: the day's Mancini levels (the validated anchor
source, st-3vu) as ``support`` anchors, plus the session range edges so
unlabeled days still surface ``range_trap`` recognitions.
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


def parsed_mancini_levels(day: _date) -> list[float]:
    """The day's levels from its own Mancini parse artifact. [st-b0n9]

    The labeled corpus (``LABELS``) stops at the hand-labeled study days, so
    every recent session — including today's, the one a live surface needs —
    resolves to no anchors at all, leaving the recognizer watching nothing but
    range edges. This reads the pre-open parse the runbook already writes.

    Prices only. The parse carries a ``kind`` per level, but ``day_anchors``
    deliberately admits every Mancini level as ``support``; carrying resistance
    through as a downward-mirrored engagement is st-tme's job, not this
    loader's, and doing it here would change what the recognizer fires on
    without the measurement that bead is holding.
    """
    path = PARSED / f"{day.isoformat()}.json"
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("could not read Mancini parse for %s (%s)", day, e)
        return []
    lv = {round(float(x["price"]), 2) for x in doc.get("levels", [])
          if isinstance(x, dict) and x.get("price") is not None
          and 5000 < float(x["price"]) < 9000}
    return sorted(lv)


def mancini_levels_for(day: _date) -> list[float]:
    """The day's Mancini support/resistance levels.

    The labeled corpus (score_recognizer.py's validated source, st-3vu) wins
    wherever it covers the day, so no labeled day's anchors move. Days it does
    not cover fall back to that day's own parse artifact — which is what makes
    a live session and a later replay of it watch the SAME anchor set instead
    of the live surface watching range edges alone. Empty when neither exists.
    """
    labeled = _labeled_levels(day)
    if labeled:
        return labeled
    parsed = parsed_mancini_levels(day)
    if parsed:
        logger.info("Mancini anchors for %s: %d from the day's parse (unlabeled day)",
                    day, len(parsed))
    return parsed


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


def day_anchors(mancini_levels: list[float], session_high: float,
                session_low: float) -> list[Anchor]:
    """Mancini levels as support anchors plus the session range edges,
    deduped on (price, kind)."""
    anchors: list[Anchor] = []
    seen: set[tuple[float, str]] = set()

    def add(price: float, kind: str, label: str, mancini: bool = False) -> None:
        key = (round(price, 2), kind)
        if key in seen:
            return
        seen.add(key)
        anchors.append(Anchor(price, kind, label, mancini=mancini))

    for lv in mancini_levels:
        add(lv, "support", f"mancini {lv:g}", mancini=True)
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

    def __init__(self, mancini_levels: list[float]):
        self.mancini = sorted(float(x) for x in mancini_levels)
        # Placeholder edges; the first bar seeds them before anything is judged.
        self.anchors = day_anchors(self.mancini, 0.0, 0.0)
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
        against the session it belongs to.
        """
        if not self._seeded:
            self._move(self._hi, bar.high)
            self._move(self._lo, bar.low)
            self._seeded = True
            return
        if bar.high > self.high.price:
            self._move(self._hi, bar.high)
        if bar.low < self.low.price:
            self._move(self._lo, bar.low)
