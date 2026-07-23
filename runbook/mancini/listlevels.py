"""Deterministic Mancini extractors — no LLM, pure text mechanics. [st-ze6]

Two rigidly-formatted sentences carry ~90% of every letter's levels:

    "Supports are: 7539, 7533 (major), 7523, … 7311 (major)."
    "Resistances are: 7547 (Major), 7554, … 7859 (major)."

``extract_list_levels`` parses them with a regex tokenizer — handles
"(major)"/"(Major)" annotations and zone shorthand like "7640-45" (expands to
7640 and 7645). It runs on EVERY pipeline pass:

  - as a count-parity cross-check against the interpretive leg (an
    interpretive parse missing a listed level = omission, fails the run), and
  - as the sole level source in hybrid mode, when the interpretive leg is
    unavailable (API credits, co-8gp) and no in-session extraction was given.

``resolve_plan_day`` reads the plan date from the letter's title line
("… July 22nd Plan", "… July 23 Plan") so ``--date`` becomes optional — the
letter itself is authoritative about which session it plans.
"""
from __future__ import annotations

import re
from datetime import date as _date

from .schema import Level

_MONTHS = {m: i + 1 for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"))}

_TITLE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(?:Trade\s+)?Plan\b")

_LIST_RE = {
    "support": re.compile(r"Supports\s+are:\s*([^.]+)\."),
    "resistance": re.compile(r"Resistances\s+are:\s*([^.]+)\."),
}

_TOKEN_RE = re.compile(
    r"^\s*(\d{3,5})(?:-(\d{1,4}))?\s*(?:\((major)\))?\s*$", re.IGNORECASE)


def resolve_plan_day(text: str, reference: _date) -> _date | None:
    """Plan date from the title ('July 23 Plan'). Year is inferred: the
    candidate (reference.year ± 1) closest to ``reference`` wins — letters
    publish the evening before, so title and blob dates straddle year-end
    at most by days, never months."""
    m = _TITLE_RE.search(text[:4000])
    if not m:
        return None
    month, day = _MONTHS[m.group(1)], int(m.group(2))
    best = None
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            cand = _date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((cand - reference).days) < abs((best - reference).days):
            best = cand
    return best


def _expand_zone(base: str, suffix: str | None) -> list[float]:
    """'7640', '45' -> [7640.0, 7645.0] (suffix replaces trailing digits)."""
    prices = [float(base)]
    if suffix:
        prices.append(float(base[: len(base) - len(suffix)] + suffix))
    return prices


def extract_list_levels(text: str) -> list[Level]:
    """Parse the Supports/Resistances list sentences into Level objects.
    Unparseable tokens are skipped (never guessed); zones yield both edges."""
    levels: list[Level] = []
    for kind, sentence_re in _LIST_RE.items():
        m = sentence_re.search(text)
        if not m:
            continue
        for token in m.group(1).split(","):
            t = _TOKEN_RE.match(token)
            if not t:
                continue
            label = "major" if t.group(3) else ""
            for price in _expand_zone(t.group(1), t.group(2)):
                levels.append(Level(price=price, kind=kind, label=label,
                                    source_quote=token.strip()))
    return levels


def parity_check(det_levels: list[Level], parsed_prices: set[float]) -> list[Level]:
    """Return deterministic list levels MISSING from an interpretive parse.
    Empty list = parity holds."""
    return [lv for lv in det_levels if lv.price not in parsed_prices]
