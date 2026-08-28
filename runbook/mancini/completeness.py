"""A floor on how *rich* a parse is, not just how correct. [st-9r51]

Stage 3. `validate.check()` proves no price was invented and
`listlevels.parity_check()` proves no *listed* level was dropped. Neither says
anything about the part of the parse Steve actually reads: what Mancini said
about the levels. The 2026-08-10 parse passed both gates carrying two callouts,
and their full text was "range high" and "range low".

**This never blocks.** A thin parse is worth publishing; a wrong one is not, and
that distinction is validation's job, not this module's. Everything here warns
and returns.

## What the floor checks, and why not what the plan said

The 08-13 plan specified two floors: every level named in the forward prose
carries a callout, and every `(major)` level carries a callout or an explicit
"none-given". Measured across 289 historical parses, the second one fires on
**every single day including the best ones** — even the richest recent parses
leave 11 to 22 of their 22 to 30 majors without a callout, because Mancini
simply does not comment on most of his ladder. A check that fires always is not
a floor, it is noise that trains you to ignore the output. It is dropped.

What does discriminate, measured on the same 289:

| signal | pre-08-11 parses | post-08-11 parses |
|---|---|---|
| prose levels absent from the ladder | 2–10 | 0 |
| prose levels carrying no callout | 3–11 | 0–2 |
| levels with a real callout | 0 | 10–20 |

So: prose coverage and callout count. The first is a genuine completeness gap
nothing else covers — `parity_check` compares against the two explicit lists
and is blind to a level Mancini names only in his bull case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import segment as segment_mod
from .schema import callout

# Prices Mancini names in prose are ES levels near his own ladder. Banding
# against the ladder is what keeps a stray four-digit number — a year, a size,
# a contract code — from being read as a level he named and reported missing.
_BAND = 0.10
_PRICE_RE = re.compile(r"(?<![\d.])(\d{4})(?:\.\d+)?(?![\d.])")

# Mancini illustrates the forward case with history, inside the forward
# sections: "it lost the June 11th low at 7325 by 1 point, recovered, and ripped
# taking 400+ points higher". 7325 is an anecdote, not a level he plans to
# trade, and it recurred in five parses in a fortnight — a warning wrong that
# often is one you learn to skip.
#
# The separator is a calendar date in the same sentence. Measured over the last
# 30 parses: 11 prose prices sit in a dated sentence and every one is that same
# anecdote; 26 sit in an undated sentence and every one is a plausible omission
# ("I'd get in low 7540's here", "Likely 7395 trigger down", "7472 and 7506
# support and 7627 resistance"). Clean split, so the rule is worth its weight.
_MONTH = (r"(?:January|February|March|April|May|June|July|August|September"
          r"|October|November|December)")
_DATE_RE = re.compile(rf"{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?", re.I)
_SENTENCE_RE = re.compile(r"[^.!?]*[.!?]|[^.!?]+$")

# Sections that carry forward-looking guidance. The bid-direct paragraph is
# deliberately NOT here: it walks the whole ladder naming levels he will not
# trade, so requiring a callout for each would fire on every letter.
PROSE_SECTIONS = ("bull_case", "bear_case", "summary")

# A callout shorter than this is 'major'/'minor'/'' — an annotation, not
# Mancini's words about the level.
MIN_CALLOUT_LEN = 6

# Floors. Set from the measured split above, not from taste: the 08-10 parse
# carried 2 rich callouts and the post-08-11 range is 10-20, so 5 separates them
# with room on both sides.
MIN_RICH_CALLOUTS = 5
MAX_PROSE_WITHOUT_CALLOUT = 2


@dataclass
class Report:
    """What the floor found. ``warnings`` is the whole user-facing output."""

    level_count: int = 0
    rich_callouts: int = 0
    prose_prices: list[float] = field(default_factory=list)
    # Prices named only inside a dated sentence — Mancini's history, not
    # his plan. Reported for transparency, never warned on.
    anecdotal_prices: list[float] = field(default_factory=list)
    prose_missing: list[float] = field(default_factory=list)
    prose_without_callout: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: bool = True  # False when the letter could not be segmented

    @property
    def ok(self) -> bool:
        """Informational only. A False here must never change an exit code."""
        return not self.warnings


def _prose_prices(seg: segment_mod.Segments, lo: float,
                  hi: float) -> tuple[list[float], list[float]]:
    """``(planned, anecdotal)`` prices from the forward prose, in band.

    A price is anecdotal when its sentence names a calendar date — see
    ``_DATE_RE`` for why that is the separator. A price that appears both ways
    counts as planned; the anecdote does not cancel the plan.
    """
    planned: set[float] = set()
    anecdotal: set[float] = set()
    for name in PROSE_SECTIONS:
        body = seg.get(name)
        if not body:
            continue
        for sm in _SENTENCE_RE.finditer(body):
            sentence = sm.group(0)
            if not sentence.strip():
                continue
            bucket = anecdotal if _DATE_RE.search(sentence) else planned
            for m in _PRICE_RE.finditer(sentence):
                v = float(m.group(0))
                if lo <= v <= hi:
                    bucket.add(v)
    return sorted(planned), sorted(anecdotal - planned)


def check(result, raw: str) -> Report:
    """Grade ``result``'s richness against the letter it came from.

    ``raw`` is the cleaned letter. Returns a Report; raises nothing, and a
    letter that cannot be segmented comes back ``checked=False`` with no
    warnings rather than a fabricated verdict.
    """
    levels = list(getattr(result, "levels", []) or [])
    rep = Report(level_count=len(levels))
    rep.rich_callouts = sum(
        1 for lv in levels if len(callout(getattr(lv, "label", ""))) > MIN_CALLOUT_LEN)

    seg = segment_mod.segment(raw)
    if not seg.anchored or not levels:
        rep.checked = False
        return rep

    prices = [float(lv.price) for lv in levels]
    lo, hi = min(prices) * (1 - _BAND), max(prices) * (1 + _BAND)
    rep.prose_prices, rep.anecdotal_prices = _prose_prices(seg, lo, hi)

    have = {float(lv.price): lv for lv in levels}
    rep.prose_missing = [p for p in rep.prose_prices if p not in have]
    rep.prose_without_callout = [
        p for p in rep.prose_prices
        if p in have and len(callout(getattr(have[p], "label", ""))) <= MIN_CALLOUT_LEN
    ]

    if rep.prose_missing:
        rep.warnings.append(
            f"{len(rep.prose_missing)} level(s) named in Mancini's forward prose "
            f"are absent from the parse entirely: "
            f"{', '.join(f'{p:g}' for p in rep.prose_missing)}. "
            f"parity_check only covers the Supports/Resistances lists, so nothing "
            f"else would have caught these.")
    if rep.rich_callouts < MIN_RICH_CALLOUTS:
        rep.warnings.append(
            f"only {rep.rich_callouts} level(s) carry a real callout "
            f"(floor {MIN_RICH_CALLOUTS}). The ladder published without the "
            f"colour Steve reads the plan for.")
    if len(rep.prose_without_callout) > MAX_PROSE_WITHOUT_CALLOUT:
        rep.warnings.append(
            f"{len(rep.prose_without_callout)} level(s) Mancini discusses in the "
            f"bull/bear/summary prose carry no callout: "
            f"{', '.join(f'{p:g}' for p in rep.prose_without_callout)}.")
    return rep


def render(rep: Report) -> str:
    """One block for the run's output. Empty string when there is nothing to say."""
    if not rep.checked:
        return ""
    if not rep.warnings:
        return (f"completeness: OK — {rep.rich_callouts} callouts, "
                f"{len(rep.prose_prices)} prose levels all present.")
    lines = ["!! COMPLETENESS FLOOR — the parse is thin. Publishing anyway."]
    lines += [f"!!   - {w}" for w in rep.warnings]
    return "\n".join(lines)
