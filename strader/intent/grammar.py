"""The deterministic extractor: a sentence of Steve's dictation becomes entities, or is
reported as not understood. Never guessed at. [st-79z.3]

The four tiers the spoken survey found in every specimen (§2.5): (1) a levels ladder,
(2) a regime keyed to a pivot, (3) opportunities as level-conditioned branches, (4) orders
and positioning. Each sentence is run through all four extractors; what no extractor
recognises goes to ``unparsed`` and is read back as "I did not understand", which is the
only honest thing to do until a real specimen teaches this file more words
(Dictation Specimen Captured, st-79z.4).

Vocabulary here is the attested vocabulary only — Mancini's letter words, the
conditions.yaml day-context tags, the scenario catalog's outcome menu, Steve's own
recorded phrases. Adding a word is a one-line change in the tables below.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from strader.intent.entities import (
    Intent, Level, Price, Regime, Setup, StructureTemplate, Trigger,
)
from strader.intent.numbers import Frame, SpokenNumber, find_numbers, small_number

# A number below this is not a price on this tape — it is a time ("ten thirty"), a count,
# or a width. ES and SPX have both been above it for years.
PRICE_FLOOR = 2000.0

SOURCE_WORDS = {"mancini": "mancini", "carmine": "carmine", "lux": "luxalgo",
                "profile": "profile", "gex": "gex", "gexbot": "gex"}

# the speaker's word -> (level kind, label kept)
LEVEL_WORDS: list[tuple[str, str]] = [
    (r"\bmajor support\b|\bsupport\b|\bshelf\b|\bfloor\b", "support"),
    (r"\bmajor resistance\b|\bresistance\b|\bceiling\b|\blid\b", "resistance"),
    (r"\bpivot\b", "pivot"),
    (r"\btarget\b|\bmagnet\b|\bpin\b|\bconsolidation\b", "target"),
    (r"\btrigger\b", "trigger"),
]
LABEL_WORDS = ("shelf", "floor", "ceiling", "lid", "magnet", "pin", "consolidation",
               "low", "high", "range low", "range high", "trigger")

DAY_TYPES: list[tuple[str, str]] = [
    (r"\bb[\s-]?day\b", "b-day"),
    (r"\btrend(?:ing)?[\s-]?(?:day\s+)?up\b|\bup[\s-]trend\b", "trend-up"),
    (r"\btrend(?:ing)?[\s-]?(?:day\s+)?down\b|\bdown[\s-]trend\b", "trend-down"),
    (r"\btrend day\b", "trend-day"),
    (r"\bchop(?:py)?\s+day\b|\brange day\b|\brange[\s-]bound day\b", "range-chop"),
    (r"\brotation\b", "rotation"),
    (r"\bliquidation\b", "liquidation"),
]
# conditions.yaml day-context tags a sentence can carry without naming the day type
TAG_WORDS: list[tuple[str, str]] = [
    (r"\bbalanc(?:e|ing|ed)\b|\bchop(?:py)?\b|\brange[\s-]bound\b|\bcoil(?:ing)?\b", "range-chop"),
    (r"\bfast\b|\bviolent\b|\bwide range\b", "vol-high"),
    (r"\bquiet\b|\bslow\b|\bdead\b", "vol-low"),
    (r"\bgap(?:ped)? up\b", "gap-up"),
    (r"\bgap(?:ped)? down\b", "gap-down"),
]
_CLAUSE_RE = re.compile(r"\s*[,;]\s*|\s+\band\b\s+(?=(?:bears|bulls)\b)")
_CONTROL_RE = re.compile(
    r"\b(bears|bulls)\b\s*(?:in\s+|have\s+|are\s+in\s+)?control\b(?:\s+(below|above|under|over))?",
    re.IGNORECASE)
_CONTROL_SHORT_RE = re.compile(r"\b(bears|bulls)\s+(below|above|under|over)\b", re.IGNORECASE)

SETUP_WORDS: list[tuple[str, str]] = [
    (r"\bfailed breakdown\b|\bfbd\b", "failed_breakdown"),
    (r"\bfailed breakout\b", "failed_breakout"),
    (r"\bbreakdown short\b", "breakdown_short"),
    (r"\blevel reclaim\b|\breclaim\b|\bretake\b", "level_reclaim"),
    (r"\blevel reject\b|\bclean reject\b|\breject(?:ion|s)?\b", "clean_reject"),
    (r"\bclean break\b", "clean_break"),
    (r"\bflush(?:es)?\s+(?:it\s+)?and\s+recover(?:s|y)?\b|\bflush and recovery\b", "flush_and_recover"),
    (r"\bv[\s-]?back\b|\bv[\s-]?down\b|\bdump and return\b|\blate flush\b|\bflush out of\b", "v_down"),
    (r"\bchop\b", "chop"),
]
_LONG_RE = re.compile(r"\b(go\s+long|long|calls?|bullish|buy)\b", re.IGNORECASE)
_SHORT_RE = re.compile(r"\b(go\s+short|short|puts?|bearish|sell)\b", re.IGNORECASE)
_ANCHOR_DOWN_RE = re.compile(
    r"\bflush(?:es|ed)?\b|\bdump\b|\bbreakdown\b|\bsell[\s-]?off\b|\bdrop\b|\bknife\b|\belevator\b|\bv[\s-]?back\b|\brecover",
    re.IGNORECASE)
_ANCHOR_UP_RE = re.compile(
    r"\bbreakout\b|\brip\b|\bsqueeze\b|\bpush(?:es)?\s+(?:above|through)\b|\bpop\b|\brally\b|\breject",
    re.IGNORECASE)
_CONDITIONAL_RE = re.compile(r"\b(if|when|once|on a|on the)\b", re.IGNORECASE)

VEHICLE_WORDS: list[tuple[str, str]] = [
    (r"\bbutterfly\b|\bflies\b|\bfly\b", "fly"),
    (r"\bsingles?\b", "single"),
    (r"\bvertical\b|\bcall spread\b|\bput spread\b", "vertical"),
    (r"\bcondor\b", "condor"),
]
_WIDTH_RE = re.compile(r"\b([a-z]+(?:[\s-][a-z]+)?|\d+)\s+wide\b", re.IGNORECASE)
_EXPIRY_RE = re.compile(r"\b(zero|one|two|\d)\s*-?\s*d\s*t\s*e\b|\b(0|1|2)dte\b|\bexpir\w+\s+(today|tomorrow)\b",
                        re.IGNORECASE)
_LOTS_RE = re.compile(r"\b([a-z]+|\d+)\s+lots?\b", re.IGNORECASE)
_CENTER_LABEL_RE = re.compile(r"\b(?:on|at|over|around)\s+the\s+(consolidation|magnet|pin|level|shelf|low|high)\b",
                              re.IGNORECASE)
_CENTER_PRICE_RE = re.compile(r"\bcent(?:er|re)(?:ed)?\s+(?:on|at)\b", re.IGNORECASE)
_ATM_RE = re.compile(r"\bat the money\b|\batm\b", re.IGNORECASE)
_FIRST_ITM_RE = re.compile(r"\bfirst (?:strike )?in the money\b|\bfirst itm\b", re.IGNORECASE)
_DELTA_RE = re.compile(r"\b(point\s+\w+|\.\d+|\d\d)\s*delta\b", re.IGNORECASE)

WINDOW_WORDS: list[tuple[str, str]] = [
    (r"\blate\b|\bafternoon\b|\blast hour\b|\binto the close\b|\blate[\s-]day\b", "window-late"),
    (r"\bfirst hour\b|\bthe open\b|\bmorning\b|\bopening\b", "window-open"),
    (r"\bmidday\b|\blunch\b|\bmid[\s-]day\b", "window-midday"),
]

_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n+")


@dataclass
class Extraction:
    """What one pass over a piece of dictation produced."""

    levels: list[Level] = field(default_factory=list)
    regime: Regime | None = None
    intents: list[Intent] = field(default_factory=list)
    structures: list[StructureTemplate] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)
    frame_notes: list[str] = field(default_factory=list)   # "6320 taken as SPX because you said so"


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text.strip()) if s.strip()]


def _source(sentence: str) -> str:
    low = sentence.lower()
    for word, src in SOURCE_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            return src
    return "manual"


def _frame_for(n: SpokenNumber, sentence: str, default: Frame, source: str | None = None) -> tuple[Frame, str]:
    """The frame a spoken number is in, and a one-line reason for the echo. ``source`` is
    the attribution read off the whole sentence when the caller is looking at one clause."""
    if n.frame:
        return n.frame, f"{n.value:g} taken as {n.frame} because you said so"
    src = source or _source(sentence)
    if src in ("mancini", "carmine"):
        return "ES", f"{n.value:g} taken as ES because it is {src.capitalize()}'s"
    return default, f"{n.value:g} taken as {default}, the day's default frame"


def _prices(sentence: str, default: Frame, source: str | None = None) -> tuple[list[Price], list[str]]:
    out, notes = [], []
    for n in find_numbers(sentence):
        if n.value < PRICE_FLOOR:
            continue
        frame, why = _frame_for(n, sentence, default, source)
        out.append(Price(value=n.value, frame=frame, said=n.text))
        notes.append(why)
    return out, notes


# ---------------------------------------------------------------- tier 1: levels

def extract_levels(sentence: str, default: Frame) -> tuple[list[Level], list[str]]:
    """Levels, clause by clause: "mancini has 6412 as the major support, bears control below
    6474" carries one level and one control clause, and the control clause's price must not
    become a second 'support'. The source (Mancini, Carmine) is read off the whole sentence."""
    src = _source(sentence)
    levels, notes = [], []
    for clause in _CLAUSE_RE.split(sentence):
        if not clause.strip() or _CONTROL_RE.search(clause) or _CONTROL_SHORT_RE.search(clause):
            continue
        prices, cnotes = _prices(clause, default, src)
        if not prices:
            continue
        low = clause.lower()
        tier = "major" if re.search(r"\bmajor\b", low) else ("minor" if re.search(r"\bminor\b", low) else "")
        kind = next((k for pattern, k in LEVEL_WORDS if re.search(pattern, low)), None)
        if kind is None:
            continue
        label = next((w for w in LABEL_WORDS if re.search(rf"\b{re.escape(w)}\b", low)), "")
        if len(prices) == 2 and re.search(r"\b(to|through|thru)\b", low):
            levels.append(Level(price=prices[0], kind=kind, tier=tier, source=src, label=label,
                                price2=prices[1], quote=sentence))
        else:
            levels += [Level(price=p, kind=kind, tier=tier, source=src, label=label, quote=sentence)
                       for p in prices]
        # the Mancini/default-frame reason for these numbers, once
        notes += cnotes
    return levels, notes


# ---------------------------------------------------------------- tier 2: regime

def extract_regime(sentence: str, default: Frame) -> tuple[Regime | None, list[Level], list[str]]:
    low = sentence.lower()
    day_type = next((t for pattern, t in DAY_TYPES if re.search(pattern, low)), "")
    tags = [t for pattern, t in TAG_WORDS if re.search(pattern, low)]
    control, pivot, pivot_levels, notes = "", None, [], []
    m = _CONTROL_RE.search(sentence) or _CONTROL_SHORT_RE.search(sentence)
    if m:
        control = m.group(1).lower()
        after = sentence[m.end():]
        src = _source(sentence)
        prices, notes = _prices(after, default, src)
        if not prices:
            # "bears control below it" — the pivot is the sentence's last named level
            prices, notes = _prices(sentence, default, src)
        if prices:
            pivot = prices[0]
            pivot_levels = [Level(price=pivot, kind="pivot", source=_source(sentence), quote=sentence)]
    if not day_type and not control and not tags:
        return None, [], []
    return Regime(day_type=day_type, control=control, pivot=pivot, tags=tags, quote=sentence), pivot_levels, notes


# ---------------------------------------------------------------- tier 3: intents

def _direction(sentence: str) -> str | None:
    # the last stated direction word wins ("... and recovers, I long for a level to level move")
    longs = [m.start() for m in _LONG_RE.finditer(sentence)]
    shorts = [m.start() for m in _SHORT_RE.finditer(sentence)]
    if not longs and not shorts:
        return None
    return "long" if (max(longs, default=-1) > max(shorts, default=-1)) else "short"


def _anchor(sentence: str, setup: str | None) -> str | None:
    low = sentence.lower()
    m = re.search(r"\bflush\s+(?:will\s+be\s+|is\s+)?(down|up)\b", low)
    if m:
        return m.group(1)
    down = _ANCHOR_DOWN_RE.search(low)
    up = _ANCHOR_UP_RE.search(low)
    if down and up:
        return "down" if down.start() < up.start() else "up"
    if down:
        return "down"
    if up:
        return "up"
    if setup in ("failed_breakdown", "level_reclaim", "flush_and_recover", "v_down", "breakdown_short"):
        return "down"
    if setup in ("failed_breakout", "level_reject", "clean_reject"):
        return "up"
    return None


def extract_intent(sentence: str, default: Frame) -> tuple[Intent | None, list[str]]:
    low = sentence.lower()
    setup = next((s for pattern, s in SETUP_WORDS if re.search(pattern, low)), None)
    direction = _direction(sentence)
    conditional = bool(_CONDITIONAL_RE.search(sentence)) or low.startswith("arm")
    if direction is None or not (setup or conditional):
        return None, []
    prices, notes = _prices(sentence, default)
    window = next((w for pattern, w in WINDOW_WORDS if re.search(pattern, low)), "")
    vehicle = next((v for pattern, v in VEHICLE_WORDS if re.search(pattern, low)), "")
    ttype = "price_zone" if re.search(r"\bzone\b|\bconsolidation\b|\brange\b", low) else \
        ("price_cross" if prices else ("time" if window else "unconditional"))
    quality = "high" if re.search(r"\bhigh[\s-]quality\b|\bbest\b|\bA\+\b", sentence) else \
        ("low" if re.search(r"\blow win rate\b|\blottery\b", low) else "")
    mgmt = "level-to-level" if re.search(r"level to level|lvl to lvl", low) else \
        ("runner" if "runner" in low else "")
    trigger = Trigger(type=ttype, anchors=prices, condition_text=sentence, namespace="steve")
    setup_obj = Setup(name=setup, anchor=prices[0] if prices else None) if setup else None
    intent = Intent(trigger=trigger, direction=direction, direction_anchor=_anchor(sentence, setup),
                    setup=setup_obj, quality=quality, window=window, management_hint=mgmt,
                    vehicle_hint=vehicle, quote=sentence)
    return intent, notes


# ---------------------------------------------------------------- tier 4: structure

def extract_structure(sentence: str, default: Frame) -> tuple[StructureTemplate | None, list[str]]:
    low = sentence.lower()
    vehicle = next((v for pattern, v in VEHICLE_WORDS if re.search(pattern, low)), None)
    if vehicle is None:
        return None, []
    width = None
    m = _WIDTH_RE.search(sentence)
    if m:
        width = small_number(m.group(1))
    expiry = "0DTE"
    m = _EXPIRY_RE.search(sentence)
    if m:
        token = (m.group(1) or m.group(2) or m.group(3) or "").lower()
        expiry = {"zero": "0DTE", "0": "0DTE", "today": "0DTE", "one": "1DTE", "1": "1DTE",
                  "tomorrow": "1DTE", "two": "2DTE", "2": "2DTE"}.get(token, "0DTE")
    right = "CALL" if re.search(r"\bcalls?\b", low) else ("PUT" if re.search(r"\bputs?\b", low) else None)
    lots = 1
    m = _LOTS_RE.search(sentence)
    if m:
        lots = small_number(m.group(1)) or 1
    center, notes = "ATM", []
    m = _CENTER_LABEL_RE.search(sentence)
    prices, pnotes = _prices(sentence, default)
    if m:
        center = m.group(1).lower()
    elif _CENTER_PRICE_RE.search(sentence) and prices:
        center = f"{prices[0].value:g}"
        notes = pnotes
    elif _ATM_RE.search(sentence):
        center = "ATM"
    delta_hint = "first-ITM" if _FIRST_ITM_RE.search(sentence) else ""
    m = _DELTA_RE.search(sentence)
    if m:
        delta_hint = m.group(1).lower()
    return StructureTemplate(vehicle=vehicle, center=center, width=width, expiry=expiry, right=right,
                             lots=lots, delta_hint=delta_hint, quote=sentence), notes


# ---------------------------------------------------------------- the pass

def extract(text: str, default_frame: Frame = "ES") -> Extraction:
    """Run every sentence through the four extractors. A sentence may yield more than one
    thing (a level and a regime call); one that yields nothing is reported, not guessed."""
    ex = Extraction()
    for s in sentences(text):
        got = False
        struct, notes = extract_structure(s, default_frame)
        if struct:
            ex.structures.append(struct); ex.frame_notes += notes; got = True
        intent, notes = extract_intent(s, default_frame)
        if intent and not struct:
            ex.intents.append(intent); ex.frame_notes += notes; got = True
        elif intent and struct:
            # "if we get the late flush ... i want the fly on the consolidation" — one sentence,
            # both an intent and a structure; keep both, and hint the intent with the vehicle
            intent.vehicle_hint = struct.vehicle
            ex.intents.append(intent); ex.frame_notes += notes
        levels, notes = extract_levels(s, default_frame)
        for lv in levels:
            if not _dup(lv, ex.levels):
                ex.levels.append(lv)
        if levels:
            ex.frame_notes += notes; got = True
        regime, pivots, notes = extract_regime(s, default_frame)
        if regime:
            ex.regime = _merge_regime(ex.regime, regime)
            ex.levels += [p for p in pivots if not _dup(p, ex.levels)]
            ex.frame_notes += notes
            got = True
        if not got:
            ex.unparsed.append(s)
    return ex


def _dup(level: Level, existing: list[Level]) -> bool:
    return any(l.price.value == level.price.value and l.price.frame == level.price.frame
               and l.kind == level.kind for l in existing)


def _merge_regime(a: Regime | None, b: Regime) -> Regime:
    if a is None:
        return b
    return Regime(day_type=b.day_type or a.day_type, control=b.control or a.control,
                  pivot=b.pivot or a.pivot, bias=b.bias or a.bias, tags=sorted(set(a.tags) | set(b.tags)),
                  quote=(a.quote + " | " + b.quote).strip(" |"))
