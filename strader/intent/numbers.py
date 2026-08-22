"""Spoken prices to numbers, and the frame every number must carry. [st-79z.3]

Traders say prices in pairs: "sixty-four twelve" is 6412, "seventy-four seventy-four" is
7474, "sixty-three hundred" is 6300, "seventy-four oh five" is 7405. Fractions follow
"and": "and a quarter" is .25, "and a half" is .50, "and three quarters" is .75. Digits
are accepted too: "6412", "6,412.25", "7412.5". Times are not prices — "ten thirty" would
parse as 1030, so the grammar only calls this where a price is expected.

This is the inverse of ``present.speech.spoken_price`` (the speech phrasebook, st-mhkp),
which turns numbers back into the same words; the two are tested against each other.

Every price carries a **frame**, ES or SPX (survey hazard #1: no code carried one, and
the ES/SPX basis gap is a known incident). A bare number's frame is resolved by the
grammar from context and echoed back; this module only records what the words said.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Frame = Literal["ES", "SPX"]

_UNITS = {
    "zero": 0, "oh": 0, "o": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_FRACTIONS = {
    "a quarter": 0.25, "quarter": 0.25, "a half": 0.5, "half": 0.5,
    "three quarters": 0.75, "three-quarters": 0.75,
}

_WORD = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|" \
        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|" \
        r"seventy|eighty|ninety|hundred|thousand)"
# a run of number words joined by spaces or hyphens, optionally followed by a fraction.
# Every word is boundary-anchored on both sides: without the trailing \b the alternation
# matches "six" inside "sixty" and the run stops there.
_SPOKEN_RE = re.compile(
    rf"\b((?:{_WORD})\b(?:[\s-]+(?:{_WORD})\b)*)"
    r"(?:\s+and\s+(a\s+quarter|quarter|a\s+half|half|three[\s-]quarters)\b)?",
    re.IGNORECASE,
)
_DIGIT_RE = re.compile(r"\b(\d{1,2},\d{3}|\d{3,5})(?:\.(\d{1,2}))?\b")
# Whisper's number normalization writes a spoken pair as a decimal now and then —
# "seventy-four forty-seven" came back as "74.47" on the 07-24 drill file (co-2a7ft).
# Two digits, a point, two digits, first group 20 or more: a pair price, not a premium
# (a debit like 1.55 has one digit before the point and never matches).
_DECIMAL_PAIR_RE = re.compile(r"\b([2-9]\d)\.(\d{2})\b")
_FRAME_AFTER_RE = re.compile(r"^\s*(spx|es)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SpokenNumber:
    """A number found in text: its value, the words that said it, and a frame if the
    speaker named one right after it ("sixty-three twenty spx")."""

    value: float
    text: str
    start: int
    end: int
    frame: Frame | None = None


def _group(words: list[str]) -> int | None:
    """One spoken group — 'sixty-four', 'twelve', 'oh five', 'hundred' — to an int."""
    total = 0
    for w in words:
        w = w.lower()
        if w in _UNITS:
            total += _UNITS[w]
        elif w in _TENS:
            total += _TENS[w]
        else:
            return None
    return total


def words_to_number(text: str) -> float | None:
    """'sixty-four twelve' -> 6412.0; 'seventy-four oh five' -> 7405.0; 'sixty-three hundred'
    -> 6300.0; 'six thousand four hundred twelve' -> 6412.0. None when the words are not a
    price shape this grammar knows."""
    words = [w for w in re.split(r"[\s-]+", text.strip().lower()) if w]
    if not words:
        return None
    if "thousand" in words:
        i = words.index("thousand")
        head = _group(words[:i])
        rest = words[i + 1:]
        if head is None:
            return None
        tail = 0
        if rest:
            if "hundred" in rest:
                j = rest.index("hundred")
                h = _group(rest[:j]) or 0
                t = _group(rest[j + 1:]) if rest[j + 1:] else 0
                if t is None:
                    return None
                tail = h * 100 + t
            else:
                t = _group(rest)
                if t is None:
                    return None
                tail = t
        return float(head * 1000 + tail)
    if "hundred" in words:
        i = words.index("hundred")
        head = _group(words[:i])
        tail = _group(words[i + 1:]) if words[i + 1:] else 0
        if head is None or tail is None:
            return None
        return float(head * 100 + tail)
    # pairs: spoken groups left to right — a tens word takes the units word after it
    # ("sixty-four" is one group), "oh five" is one group, a teen or a unit stands alone.
    # One group is a plain number; two groups are a price pair ("sixty-four twelve").
    groups = _groups(words)
    if groups is None or not groups:
        return None
    if len(groups) == 1:
        return float(groups[0])
    if len(groups) == 2:
        return float(groups[0] * 100 + groups[1])
    return None


def _groups(words: list[str]) -> list[int] | None:
    groups: list[int] = []
    i = 0
    while i < len(words):
        w = words[i].lower()
        nxt = words[i + 1].lower() if i + 1 < len(words) else None
        if w in _TENS:
            val = _TENS[w]
            if nxt in _UNITS and 1 <= _UNITS[nxt] <= 9:
                val += _UNITS[nxt]
                i += 1
            groups.append(val)
        elif w in ("oh", "zero", "o"):
            if nxt in _UNITS and 1 <= _UNITS[nxt] <= 9:
                groups.append(_UNITS[nxt])
                i += 1
            else:
                groups.append(0)
        elif w in _UNITS:
            groups.append(_UNITS[w])
        else:
            return None
        i += 1
    return groups


def find_numbers(text: str) -> list[SpokenNumber]:
    """Every spoken or digit price in ``text``, left to right, with spans and any frame
    word that directly follows ("... spx")."""
    out: list[SpokenNumber] = []
    for m in _DIGIT_RE.finditer(text):
        whole = m.group(1).replace(",", "")
        frac = m.group(2)
        value = float(whole) + (float(f"0.{frac}") if frac else 0.0)
        out.append(_with_frame(text, SpokenNumber(value, m.group(0), m.start(), m.end())))
    for m in _DECIMAL_PAIR_RE.finditer(text):
        value = float(m.group(1)) * 100 + float(m.group(2))
        out.append(_with_frame(text, SpokenNumber(value, m.group(0), m.start(), m.end())))
    for m in _SPOKEN_RE.finditer(text):
        value = words_to_number(m.group(1))
        if value is None or value < 100:       # a lone "twenty" is a width, not a price
            continue
        if m.group(2):
            value += _FRACTIONS[re.sub(r"\s+", " ", m.group(2).lower().replace("-", " "))]
        out.append(_with_frame(text, SpokenNumber(value, m.group(0), m.start(), m.end())))
    out.sort(key=lambda n: n.start)
    return out


def _with_frame(text: str, n: SpokenNumber) -> SpokenNumber:
    m = _FRAME_AFTER_RE.match(text[n.end:])
    if m:
        return SpokenNumber(n.value, n.text, n.start, n.end + m.end(), m.group(1).upper())
    return n


def small_number(text: str) -> int | None:
    """A count or width said in words or digits — 'twenty', 'two', '20', '3'. None if absent."""
    m = re.search(r"\b(\d{1,3})\b", text)
    if m:
        return int(m.group(1))
    words = re.findall(_WORD, text.lower())
    if words:
        v = _group(words[:2])
        if v is not None and v < 1000:
            return v
    return None
