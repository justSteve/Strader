"""The spoken door to a region replay: one sentence → a region and a filter. [co-j9t1g]

Steve's request (Desk memo 20260826T013442): *"replay Monday 13:30 to 14:10,
sweeps and plan-level only."* The keyboard form and the spoken form are the
same parameters, and the chart's shift-drag fills in this same sentence, so
there is exactly one way a region is described anywhere in the estate.

Deterministic, like the rest of the dialect (Steve's harness-first rule): a
word this file does not know is reported in ``unknown`` and read back as such,
never guessed at. The kind words come from ``market.orderflow.region_replay``
so the vocabulary has one home; adding a word there adds it here.

What a sentence may carry, in any order:

  a day       today · yesterday · Monday … Friday · last Tuesday · 2026-08-25
              · 8/25 · aug 25 — absent means the day the caller supplies
              (the page's day, or today)
  a window    13:30 to 14:10 · 1:30-2:10 · from 13:30 · after 13:30 · before
              10:00 · around 13:45 · at 13:45 · first hour · the open · last
              hour · into the close · midday · morning · afternoon · rth /
              cash session · overnight. Clock hours below 8 with no am/pm are
              afternoon (1:30 is 13:30) — nothing trades at 01:30 that he
              wants replayed by the clock.
  a band      7680 to 7695 · between 7680 and 7695 · around 7686 (±5) · at
              7686 (±2) · above 7680 · below 7690 — spoken prices too
              ("seventy-six eighty"), via the dialect's number reader
  kinds       sweeps · plan-level · stacks · setups · divergences ·
              absorption · climax · superlatives · profile levels — "only"
              and "and" are noise; no kind word means everything
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from strader.intent.numbers import find_numbers

CT = ZoneInfo("America/Chicago")

# Below this a number is a clock or a count, not a price on this tape.
PRICE_FLOOR = 2000.0
RTH_OPEN = time(8, 30)
RTH_CLOSE = time(15, 0)
DAY_START = time(0, 0)
DAY_END = time(23, 59)

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
            "saturday": 5, "sunday": 6}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9

# Named windows, longest phrase first so "into the close" wins over "close".
NAMED_WINDOWS: list[tuple[str, tuple[time, time]]] = [
    (r"\binto the close\b|\bthe close\b|\bclosing hour\b", (time(14, 0), RTH_CLOSE)),
    (r"\blast hour\b|\bfinal hour\b", (time(14, 0), RTH_CLOSE)),
    (r"\bfirst hour\b|\bopening hour\b", (RTH_OPEN, time(9, 30))),
    (r"\bthe open\b|\bopening\b", (RTH_OPEN, time(9, 0))),
    (r"\bmid-?day\b|\blunch\b", (time(11, 0), time(13, 0))),
    (r"\bmorning\b", (RTH_OPEN, time(12, 0))),
    (r"\bafternoon\b", (time(12, 0), RTH_CLOSE)),
    (r"\brth\b|\bcash session\b|\bday session\b|\bregular session\b", (RTH_OPEN, RTH_CLOSE)),
    (r"\bovernight\b|\bglobex\b|\bpre-?market\b", (DAY_START, RTH_OPEN)),
    (r"\bwhole day\b|\ball day\b|\bfull day\b", (DAY_START, DAY_END)),
]

_TIME = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"
_TIME_RE = re.compile(r"(?<![\d.])" + _TIME + r"(?![\d.])", re.IGNORECASE)
_RANGE_RE = re.compile(
    r"\b(?:from\s+|between\s+)?" + _TIME + r"\s*(?:to|-|–|through|thru|until|till|and)\s*" + _TIME
    + r"(?![\d.])", re.IGNORECASE)
_AFTER_RE = re.compile(r"\b(after|from|since)\s+" + _TIME + r"(?![\d.])", re.IGNORECASE)
_BEFORE_RE = re.compile(r"\b(before|until|till|up to)\s+" + _TIME + r"(?![\d.])", re.IGNORECASE)
_AROUND_RE = re.compile(r"\b(around|about|near|at)\s+" + _TIME + r"(?![\d.])", re.IGNORECASE)
_HHMM_RE = re.compile(r"\b([01]\d|2[0-3])([0-5]\d)\b")

_HHMM_RANGE_RE = re.compile(
    r"\b([01]\d|2[0-3])([0-5]\d)\s*(?:to|-|–|through|thru|until|till|and)\s*([01]\d|2[0-3])([0-5]\d)\b")

_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# Slash only: "8-25" would collide with a clock range ("8-9") and is not how
# a date is said aloud; "8/25" and "August 25" are.
_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_MONTH_RE = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True))
                       + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)
_WEEKDAY_RE = re.compile(r"\b(?:last\s+|this\s+|on\s+)?(" + "|".join(WEEKDAYS) + r")\b", re.IGNORECASE)

# Matched against the words immediately BEFORE a lone price, so anchored at
# the end: "... above " → above.
_PRICE_AROUND_RE = re.compile(r"\b(around|about|near|at)\s*$", re.IGNORECASE)
_PRICE_ABOVE_RE = re.compile(r"\b(above|over)\s*$", re.IGNORECASE)
_PRICE_BELOW_RE = re.compile(r"\b(below|under)\s*$", re.IGNORECASE)

NOISE = {"replay", "show", "me", "the", "a", "an", "of", "on", "for", "with", "and",
         "only", "just", "emissions", "emission", "events", "event", "everything", "all",
         "please", "run", "again", "in", "ct", "central", "prices", "price", "points",
         "between", "from", "to", "through", "thru", "until", "till", "after", "before",
         "around", "about", "near", "at", "above", "over", "below", "under", "last",
         "this", "session", "window", "region", "what", "would", "have", "said", "fired",
         "that", "there", "then", "am", "pm", "es", "spx", "level", "levels", "band"}


@dataclass(frozen=True)
class ReplayRequest:
    """One sentence, understood. Values only — the region/filter objects are
    built by the caller that owns the playback engine."""

    day: date
    end: date | None = None
    between: tuple[time, time] | None = None
    price_band: tuple[float, float] | None = None
    kinds: frozenset[str] = frozenset()
    unknown: tuple[str, ...] = ()
    text: str = ""
    day_word: str = ""       # what named the day, for the read-back ("Monday", "yesterday")

    def as_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "between": [t.strftime("%H:%M") for t in self.between] if self.between else None,
            "price_band": list(self.price_band) if self.price_band else None,
            "kinds": sorted(self.kinds),
            "unknown": list(self.unknown),
            "text": self.text,
        }


class ReplayParseError(ValueError):
    """The sentence cannot be turned into a region at all (a window that runs
    backwards, a date that does not exist). Unknown words are NOT this — they
    are reported on the request and the replay still runs."""


# ── pieces ─────────────────────────────────────────────────────────────────

def _clock(h: str, m: str | None, ap: str | None) -> time:
    hour, minute = int(h), int(m or 0)
    if hour > 23 or minute > 59:
        raise ReplayParseError(f"not a clock time: {h}:{m or '00'}")
    ap = (ap or "").replace(".", "").lower()
    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    elif not ap and 0 < hour < 8:
        # No am/pm and before eight: the afternoon. "1:30 to 2:10" is the
        # cash session, never the small hours.
        hour += 12
    return time(hour, minute)


def _extract_window(text: str) -> tuple[tuple[time, time] | None, str]:
    """The intra-day window and the text with the clock words blanked."""
    for pat, win in NAMED_WINDOWS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return win, text[:m.start()] + " " + text[m.end():]
    m = _HHMM_RANGE_RE.search(text)
    if m:
        lo = _clock(m.group(1), m.group(2), None)
        hi = _clock(m.group(3), m.group(4), None)
        if hi < lo:
            raise ReplayParseError(f"window runs backwards: {lo:%H:%M} to {hi:%H:%M}")
        return (lo, hi), text[:m.start()] + " " + text[m.end():]
    m = _RANGE_RE.search(text)
    if m:
        lo = _clock(m.group(1), m.group(2), m.group(3))
        hi = _clock(m.group(4), m.group(5), m.group(6))
        if hi < lo:
            raise ReplayParseError(f"window runs backwards: {lo:%H:%M} to {hi:%H:%M}")
        return (lo, hi), text[:m.start()] + " " + text[m.end():]
    m = _AFTER_RE.search(text)
    if m:
        return (_clock(m.group(2), m.group(3), m.group(4)), DAY_END), text[:m.start()] + " " + text[m.end():]
    m = _BEFORE_RE.search(text)
    if m:
        return (DAY_START, _clock(m.group(2), m.group(3), m.group(4))), text[:m.start()] + " " + text[m.end():]
    m = _AROUND_RE.search(text)
    if m:
        t = _clock(m.group(2), m.group(3), m.group(4))
        pad = 10 if m.group(1).lower() != "at" else 5
        lo = (datetime.combine(date.min, t) - timedelta(minutes=pad)).time() if t > time(0, pad) else DAY_START
        hi = (datetime.combine(date.min, t) + timedelta(minutes=pad)).time() if t < time(23, 59 - pad) else DAY_END
        return (lo, hi), text[:m.start()] + " " + text[m.end():]
    m = _HHMM_RE.search(text)
    if m:
        t = _clock(m.group(1), m.group(2), None)
        return (t, DAY_END), text[:m.start()] + " " + text[m.end():]
    return None, text


def _extract_slash_day(text: str, today: date) -> tuple[date | None, str, str]:
    """"8/25" — read AFTER the clock words are gone, so a range can never be
    mistaken for a date or the reverse."""
    m = _SLASH_RE.search(text)
    if m and int(m.group(1)) <= 12:
        year = today.year
        if m.group(3):
            year = int(m.group(3))
            year = year + 2000 if year < 100 else year
        try:
            d = date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            raise ReplayParseError(f"no such date: {m.group(0)}") from None
        return d, m.group(0), text[:m.start()] + " " + text[m.end():]
    return None, "", text


def _extract_day(text: str, today: date) -> tuple[date | None, str, str]:
    """The day named by a word or a full date, the word that named it, and
    the text without it. Slash dates are read separately, after the clock."""
    m = _ISO_RE.search(text)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            raise ReplayParseError(f"no such date: {m.group(0)}") from None
        return d, m.group(0), text[:m.start()] + " " + text[m.end():]
    m = _MONTH_RE.search(text)
    if m:
        month = MONTHS[m.group(1).lower().rstrip(".")]
        year = today.year if month <= today.month else today.year - 1
        try:
            d = date(year, month, int(m.group(2)))
        except ValueError:
            raise ReplayParseError(f"no such date: {m.group(0)}") from None
        return d, m.group(0), text[:m.start()] + " " + text[m.end():]
    m = re.search(r"\byesterday\b", text, re.IGNORECASE)
    if m:
        d = today - timedelta(days=1)
        while d.weekday() > 4:          # a Monday's yesterday is Friday
            d -= timedelta(days=1)
        return d, "yesterday", text[:m.start()] + " " + text[m.end():]
    m = re.search(r"\btoday\b", text, re.IGNORECASE)
    if m:
        return today, "today", text[:m.start()] + " " + text[m.end():]
    m = _WEEKDAY_RE.search(text)
    if m:
        want = WEEKDAYS[m.group(1).lower()]
        back = (today.weekday() - want) % 7
        d = today - timedelta(days=back)
        return d, m.group(1).capitalize(), text[:m.start()] + " " + text[m.end():]
    return None, "", text


def _extract_band(text: str) -> tuple[tuple[float, float] | None, str]:
    """A price band from the prices left after the clock words are gone."""
    nums = [n for n in find_numbers(text) if n.value >= PRICE_FLOOR]
    if not nums:
        return None, text
    blank = lambda s, n: s[:n.start] + " " * (n.end - n.start) + s[n.end:]  # noqa: E731
    if len(nums) >= 2:
        a, b = nums[0], nums[1]
        lo, hi = sorted((a.value, b.value))
        out = blank(blank(text, b), a)
        out = re.sub(r"\b(between|from)\s+(?=\s)", " ", out, flags=re.IGNORECASE)
        return (lo, hi), out
    n = nums[0]
    before = text[:n.start][-12:]
    out = blank(text, n)
    if _PRICE_ABOVE_RE.search(before):
        return (n.value, n.value + 10_000), out
    if _PRICE_BELOW_RE.search(before):
        return (n.value - 10_000, n.value), out
    m = _PRICE_AROUND_RE.search(before)
    pad = 2.0 if (m and m.group(1).lower() == "at") else 5.0
    return (n.value - pad, n.value + pad), out


def _extract_kinds(text: str) -> tuple[frozenset[str], str]:
    from market.orderflow.region_replay import KIND_WORDS  # heavy import, on demand
    kinds: set[str] = set()
    out = text
    for word in sorted(KIND_WORDS, key=len, reverse=True):
        pat = r"\b" + re.escape(word).replace(r"\ ", r"[\s-]+") + r"\b"
        m = re.search(pat, out, re.IGNORECASE)
        while m:
            kinds.update(KIND_WORDS[word])
            out = out[:m.start()] + " " + out[m.end():]
            m = re.search(pat, out, re.IGNORECASE)
    return frozenset(kinds), out


def _leftover(text: str) -> tuple[str, ...]:
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]*", text)
    return tuple(w for w in words if w.lower() not in NOISE)


# ── the sentence ───────────────────────────────────────────────────────────

def parse_replay(text: str, *, today: date | None = None,
                 default_day: date | None = None) -> ReplayRequest:
    """One sentence → a request. ``today`` anchors relative day words (the
    caller passes it so tests are deterministic); ``default_day`` is the day
    when the sentence names none — the page's day, or today."""
    today = today or datetime.now(CT).date()
    raw = text.strip()
    s = " " + re.sub(r"\s+", " ", raw) + " "
    day, day_word, s = _extract_day(s, today)
    window, s = _extract_window(s)
    if day is None:
        day, day_word, s = _extract_slash_day(s, today)
    band, s = _extract_band(s)
    kinds, s = _extract_kinds(s)
    unknown = _leftover(s)
    return ReplayRequest(
        day=day or default_day or today, between=window, price_band=band,
        kinds=kinds, unknown=unknown, text=raw, day_word=day_word,
    )


def readback(req: ReplayRequest, *, speak: bool = False) -> str:
    """What will be replayed, in a sentence Steve can check by ear."""
    from market.orderflow.region_replay import KIND_LABEL  # on demand, see above
    day = req.day.strftime("%A %Y-%m-%d") if speak else f"{req.day:%a} {req.day.isoformat()}"
    if req.day_word and req.day_word.lower() in ("yesterday", "today"):
        day = f"{req.day_word} ({req.day.isoformat()})"
    parts = [f"Replay {day}"]
    if req.between:
        lo, hi = req.between
        if (lo, hi) == (DAY_START, DAY_END):
            parts.append("the whole day")
        else:
            parts.append(f"{lo:%H:%M} to {hi:%H:%M} CT")
    else:
        parts.append("the whole day")
    if req.price_band:
        lo, hi = req.price_band
        if lo < 0:
            parts.append(f"below {hi:g}")
        elif hi - lo >= 10_000:
            parts.append(f"above {lo:g}")
        else:
            parts.append(f"prices {lo:g} to {hi:g}")
    if req.kinds:
        parts.append(" and ".join(KIND_LABEL.get(k, k) for k in sorted(req.kinds)) + " only")
    else:
        parts.append("everything")
    out = ", ".join(parts) + "."
    if req.unknown:
        out += " Not understood: " + ", ".join(req.unknown) + "."
    return out
