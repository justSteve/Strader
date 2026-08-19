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

``resolve_plan_day_full`` is the backfill's resolver [co-vp45h]: it reads the
whole cache of letters, where the title is not always a clean "Month Day
Plan" ("July 28.", "Sept 4th Plan", "January 19/20 Plan", "April 18 Plan" on
a Friday letter — a typo for the 20th, truncated emails with no title at
all), so it returns a date for every letter plus the name of the rule that
produced it, and the caller records the rule beside the artifact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .schema import Level

CENTRAL = ZoneInfo("America/Chicago")

_MONTHS = {m: i + 1 for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"))}
_MONTH_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
               "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}

_TITLE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(?:Trade\s+)?Plan\b")

# The plan date is the LAST month-day in the title, at its end: "… Since July
# 15th. Will It Get Bought? July 29 Plan" names the 29th, not the 15th. A
# title whose only date is mid-sentence ("Can July 4th Seasonals Hold?") has
# no plan date and falls through. "19/20" (holiday/next day) carries both.
_ORD = r"(?:st|nd|rd|th)?"
_TITLE_END_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?\s+"
    r"(\d{1,2})" + _ORD + r"(?:\s*/\s*(\d{1,2})" + _ORD + r")?,?\s*"
    r"(?:Trade\s+)?(?:Plan)?\s*[.?!]*\s*$", re.IGNORECASE)
_WEEKDAY_HDR_RE = re.compile(r"Trade\s+Plan\s+(Monday|Tuesday|Wednesday|Thursday|Friday)\b")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# A letter sent before this (CT) on a weekday is the plan for that same day
# (the 02:58 CT 2026-07-17 send); after it, the plan is for the next session.
_SAME_DAY_CUTOFF_CT = time(8, 30)
# A title date further than this from the send date is a typo ("June 17
# Plan" on the July 16th letter) and the title is not trusted for that letter.
_MAX_TITLE_GAP_DAYS = 4

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


# ------------------------------------------------------------ full resolver

@dataclass(frozen=True)
class PlanDay:
    """``resolve_plan_day_full``'s answer: the session the letter plans, the
    rule that decided it, and the title line it read. ``confidence`` orders
    the rules (higher wins when resends of one letter disagree)."""
    day: _date
    rule: str          # "title" | "weekday-header" | "next-session"
    title: str
    confidence: int    # 3 title, 2 weekday header, 1 next session
    also: _date | None = None   # a "July 3rd/6th Plan" letter plans the second day too


def title_line(text: str) -> str:
    """The letter's headline. Substack's visible text puts it on the first
    non-empty line after the "View in browser" link; a letter without that
    marker (a forwarded copy) has no findable title and gets ''."""
    lines = text.splitlines()
    for i, line in enumerate(lines[:80]):
        if line.strip().lower() == "view in browser":
            for nxt in lines[i + 1:i + 6]:
                if nxt.strip():
                    return nxt.strip()
            break
    return ""


def _nearest_year(month: int, day: int, reference: _date) -> _date | None:
    best = None
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            cand = _date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((cand - reference).days) < abs((best - reference).days):
            best = cand
    return best


def _first_session_after(sent_at: datetime) -> _date:
    """The session a letter plans when nothing in it says otherwise: the
    send day itself when sent before the open on a weekday, else the next
    weekday. ``sent_at`` must be tz-aware."""
    local = sent_at.astimezone(CENTRAL)
    d = local.date()
    if d.weekday() < 5 and local.time() < _SAME_DAY_CUTOFF_CT:
        return d
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _plausible(day: _date, sent_at: datetime) -> bool:
    """A plan date is believable when it is a weekday no more than
    ``_MAX_TITLE_GAP_DAYS`` after the send, and not before it (a same-day date
    needs the before-open send)."""
    if day.weekday() >= 5:
        return False
    gap = (day - sent_at.astimezone(CENTRAL).date()).days
    if gap == 0:
        return sent_at.astimezone(CENTRAL).time() < _SAME_DAY_CUTOFF_CT
    return 0 < gap <= _MAX_TITLE_GAP_DAYS


def _title_trusted(day: _date, sent_at: datetime, header_weekday: int | None) -> bool:
    """Is the title's date the letter's plan date, or a typo?

    Typos seen in the cache: "April 18 Plan" on a Friday letter (a Saturday;
    the 20th was meant), "April 5th Plan" sent May 5th, "June 17 Plan" sent
    July 16th, "August 15 Plan" on a Friday. Forwarded copies of OLD letters
    (the 2026-07-17 batch re-sent "July 7th Plan" … "July 16 Plan") are not
    typos — their titles are right and the send date is not.

    The body's "Trade Plan <Weekday>" header tells them apart: a real plan
    date falls on that weekday; a typo almost never does. Without a header,
    the date has to sit where a plan date sits relative to the send.
    """
    if day.weekday() >= 5:
        return False
    gap = (day - sent_at.astimezone(CENTRAL).date()).days
    if gap > _MAX_TITLE_GAP_DAYS:
        return False
    if header_weekday is not None:
        return day.weekday() == header_weekday
    return _plausible(day, sent_at)


def resolve_plan_day_full(text: str, sent_at: datetime,
                          has_session=None) -> PlanDay:
    """Which session does this letter plan? Always answers. [co-vp45h]

    1. The title's trailing month-day ("… Sept 4th Plan", "… July 28."),
       when ``_title_trusted`` says it is not a typo. "19/20" names a
       holiday and the day after: the first that ``has_session`` confirms
       (when given), else the second.
    2. The body's "Trade Plan <Weekday>" header — the next such weekday
       after the send, when it is within reach.
    3. The first session after the send (same day if sent before the open).

    ``has_session(date) -> bool`` is optional (the tape corpus, in the
    backfill); without it rule 1 takes the later of a pair.
    """
    if sent_at.tzinfo is None:
        raise ValueError("sent_at must be tz-aware")
    title = title_line(text)
    hdr = _WEEKDAY_HDR_RE.search(text)
    header_weekday = _WEEKDAYS.index(hdr.group(1).lower()) if hdr else None
    m = _TITLE_END_RE.search(title)
    if m:
        key = m.group(1).lower()
        month = _MONTHS.get(m.group(1).capitalize()) or _MONTH_ABBR.get(key)
        ref = sent_at.astimezone(CENTRAL).date()
        cands = [_nearest_year(month, int(g), ref) for g in (m.group(2), m.group(3)) if g]
        cands = [c for c in cands if c is not None]
        if len(cands) == 2:
            # "Nov 27/28 Plan": a holiday and the session after it. The
            # header names one of the two (either is fine); the session the
            # tape confirms is the plan day, else the later.
            first, second = cands
            trusted = (_title_trusted(first, sent_at, header_weekday)
                       or _title_trusted(second, sent_at, header_weekday))
            first_trades = has_session is not None and has_session(first)
            pick = first if first_trades else second
            # Both trade ("July 3rd/6th": a half day and the Monday): the
            # letter is the plan for both; the caller may file it twice.
            also = second if (first_trades and has_session(second)) else None
            if trusted and pick.weekday() < 5:
                return PlanDay(pick, "title", title, 3, also)
        elif cands and _title_trusted(cands[0], sent_at, header_weekday):
            return PlanDay(cands[0], "title", title, 3)
    if header_weekday is not None:
        local = sent_at.astimezone(CENTRAL)
        d = local.date()
        if not (d.weekday() == header_weekday and local.time() < _SAME_DAY_CUTOFF_CT):
            d += timedelta(days=1)
            while d.weekday() != header_weekday:
                d += timedelta(days=1)
        if _plausible(d, sent_at):
            return PlanDay(d, "weekday-header", title, 2)
    return PlanDay(_first_session_after(sent_at), "next-session", title, 1)


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
