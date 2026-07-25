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

LABELS = (Path(__file__).resolve().parent.parent.parent
          / "docs/measurement/mancini-setup-labels-2026-07-06.json")
FAMILY = {"failed_breakdown", "level_reclaim"}


def mancini_levels_for(day: _date) -> list[float]:
    """The day's Mancini support/resistance levels from the labeled corpus —
    the same anchor source score_recognizer.py validated against. Empty for
    unlabeled days (callers then fall back to session range edges)."""
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
