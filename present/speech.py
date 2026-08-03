"""Render emitted Signals as sentences meant to be *heard*.

``present/signals.py`` formats the same objects for the eye — a tmux pane you
scan. This module is its ear-side twin, and it is deliberately a separate
rendering rather than a reuse of ``Signal.reason``:

1. ``reason`` is written to be read, in measurement-harness vocabulary.
   ``docs/training/plain-words-glossary.md`` (st-v95) exists precisely because
   that vocabulary reached Steve undefined. The glossary is the authority for
   every word chosen here.
2. Prices must be spoken the way a trader says them. "7438.25" read literally
   is "seven thousand four hundred thirty eight point two five" — wrong idiom,
   and too slow to be useful while the tape is moving.
3. LIVE vs HINDSIGHT is a safety property. The glossary marks percentiles,
   cells, legs and archetypes as HINDSIGHT — computable only once the day
   completes. Speaking one in real time asserts something unknowable, so
   :func:`speak` refuses to emit them at all.

Scope: a pure function, ``Signal -> str | None``. ``None`` means "no phrasing
for this", never a guess. What is *worth* saying, how utterances queue, what
gets dropped when speech falls behind the tape, and the reader process itself
are all separate concerns and separate beads.

Bead: st-mhkp. Audio substrate proven under COO co-fsg5p.
"""
from __future__ import annotations

import logging

from market.signals.types import (
    Signal, Bias, Regime, Level, Alert, Action, InferenceRequest,
)
from market.signals.orderflow import (
    SweepPrint, DeltaDivergence, ImbalanceStack, AbsorptionRead,
    SetupRecognition,
)

log = logging.getLogger(__name__)

__all__ = ["speak", "spoken_price", "spoken_count", "HindsightLeak"]


# --------------------------------------------------------------------------
# Numbers
#
# Number words are generated here rather than handed to the TTS engine as
# digits. espeak-ng, piper and any cloud voice each read "74" and "7438.25"
# differently; generating the words in-process makes output engine-independent
# and testable without audio.
# --------------------------------------------------------------------------

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = (
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
)

# ES trades in quarter points. Anything else is spoken digit-wise rather than
# silently rounded onto a tick that the instrument may not have.
_FRACTIONS = {0: "", 25: " and a quarter", 50: " and a half", 75: " and three quarters"}


def _under_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_ONES[ones]}"


def spoken_count(n: int) -> str:
    """A plain cardinal, for sizes and tick counts. Falls back to digits above
    999 — every engine reads large integers acceptably, and spelling them out
    makes a sentence longer than the move it describes."""
    if n < 0:
        return f"minus {spoken_count(-n)}"
    if n < 100:
        return _under_hundred(n)
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = f"{_ONES[hundreds]} hundred"
        return head if rest == 0 else f"{head} {_under_hundred(rest)}"
    return str(n)


def spoken_price(price: float) -> str:
    """Speak a price the way a trader says it.

    >>> spoken_price(7438.0)
    'seventy-four thirty-eight'
    >>> spoken_price(7438.25)
    'seventy-four thirty-eight and a quarter'
    >>> spoken_price(7400.0)
    'seventy-four hundred'
    >>> spoken_price(7405.0)
    'seventy-four oh five'
    """
    whole = int(price)
    cents = round(round(price - whole, 2) * 100)
    if cents == 100:            # 7437.999 -> 7438.0
        whole, cents = whole + 1, 0

    tail = _FRACTIONS.get(cents)
    if tail is None:
        # Not on a quarter. Say the decimal rather than round it away — a
        # non-ES instrument's real price beats a tidy ES-shaped lie.
        tail = f" point {''.join(_ONES[int(d)] + ' ' for d in f'{cents:02d}').strip()}"

    # The four-digit pair form ("seventy-four thirty-eight") is how ES and SPX
    # are spoken. Outside that range it stops being idiomatic, so fall back.
    if 1000 <= whole < 10000:
        hi, lo = divmod(whole, 100)
        if whole % 1000 == 0:
            # 7400 is "seventy-four hundred", but 7000 is "seven thousand" —
            # nobody says "seventy hundred".
            head = f"{_ONES[whole // 1000]} thousand"
        elif lo == 0:
            head = f"{_under_hundred(hi)} hundred"
        elif lo < 10:
            head = f"{_under_hundred(hi)} oh {_ONES[lo]}"
        else:
            head = f"{_under_hundred(hi)} {_under_hundred(lo)}"
    else:
        head = spoken_count(whole)

    return head + tail


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

# The recognizer's four stages, in the glossary's plain words. The frozen
# tokens (flush/stall/flip/confirm) are a record contract [st-g9y] and must
# never be spoken as-is — they are exactly the jargon st-v95 was raised over.
_BEATS = {
    "flush":   "pushed through",
    "stall":   "failed to hold",
    "flip":    "the delta turned",
    "confirm": "came back through",
}

_ANCHOR_KINDS = {
    "support":    "support",
    "resistance": "resistance",
    "range_high": "the range high",
    "range_low":  "the range low",
    "lvn":        "a thin shelf",
}

# Confidence is spoken as a word only when the recognizer has guarded it.
# Undamped confirms score 0.8 (0.9 stacked); at fire_index >= 4 the recognizer
# step-damps to 0.6 (0.7 stacked) — see market/orderflow/recognizer.py. This
# threshold sits between those two bands and exists to name that damping out
# loud, not to invent a grading of its own.
_CONF_GUARDED = 0.75

# Quantities the glossary marks HINDSIGHT — knowable only after the day
# completes. None of the LIVE signal types below carry them; this net exists so
# that a future subclass cannot start narrating them by accident.
_HINDSIGHT_TOKENS = (
    "percentile", "archetype", "flush-leg", "steady-leg", "leg-grind",
    "counterforce-leg", "absorption-stall", "hollow-glide", "probe-fade",
    "dead-drift", "pivot-atom", "grade-band", "coin-flip",
)


class HindsightLeak(AssertionError):
    """Raised when a phrasing would speak a quantity that is only knowable
    after the session ends. A bug in a phrasing function, never user input."""


# --------------------------------------------------------------------------
# Phrasings
# --------------------------------------------------------------------------

def _setup_recognition(s: SetupRecognition) -> str:
    side = "Buy" if s.bias == "bullish" else "Sell"
    where = spoken_price(s.anchor_price)
    kind = _ANCHOR_KINDS.get(s.anchor_kind, s.anchor_kind.replace("_", " "))

    if s.state == "invalidated":
        return f"{where} is off. The setup there failed."

    if s.state == "forming":
        beats = [_BEATS[b] for b in s.beats if b in _BEATS]
        seen = ", ".join(beats) if beats else "still early"
        return f"Setting up at {where}, {kind}. So far: {seen}. Not confirmed."

    # confirmed
    parts = [f"{side} signal at {where}, {kind}."]
    if s.fire_index > 1:
        # st-m3f: the fourth fire at a level is a materially different call
        # from the first. A voice that hides the count is misleading.
        parts.append(f"That is {_ordinal(s.fire_index)} time at this level today.")
    if s.mancini_confluence:
        parts.append("It is a Mancini level.")
    if s.confidence < _CONF_GUARDED:
        parts.append("Lower confidence.")
    return " ".join(parts)


_ORDINALS = {
    1: "the first", 2: "the second", 3: "the third", 4: "the fourth",
    5: "the fifth", 6: "the sixth", 7: "the seventh", 8: "the eighth",
    9: "the ninth", 10: "the tenth",
}


def _ordinal(n: int) -> str:
    return _ORDINALS.get(n, f"the {spoken_count(n)}th")


def _sweep_print(s: SweepPrint) -> str:
    side = "Buy" if s.direction == "buy" else "Sell"
    return (
        f"{side} sweep, {spoken_count(s.ticks_swept)} ticks through "
        f"to {spoken_price(s.end_price)}, {spoken_count(s.total_size)} contracts."
    )


def _delta_divergence(s: DeltaDivergence) -> str:
    extreme = "high" if s.kind == "bearish" else "low"
    return (
        f"Divergence at {spoken_price(s.price_extreme)}. "
        f"New {extreme}, but the aggression did not follow."
    )


def _imbalance_stack(s: ImbalanceStack) -> str:
    side = "Buy" if s.direction == "buy" else "Sell"
    levels = len(s.prices)
    if not levels:
        return f"{side} stack."
    span = spoken_price(s.prices[0])
    if levels > 1:
        span += f" to {spoken_price(s.prices[-1])}"
    return f"{side} stack, {spoken_count(levels)} levels, {span}."


def _absorption_read(s: AbsorptionRead) -> str:
    who = "Buyers" if s.side == "bid" else "Sellers"
    where = spoken_price(s.price)
    took = f"took {spoken_count(s.aggressive_vol)} contracts"

    if s.displacement_ticks > 0:
        outcome = "and held. Price lifted away."
    elif s.displacement_ticks < 0:
        outcome = "and the level broke."
    else:
        outcome = "and it has not resolved."

    line = f"{who} defended {where}, {took} {outcome}"
    if s.refill_events == 0:
        # Trades-only mode: no MBP-1 quotes, so the refill evidence is absent.
        # Say so rather than let the sentence imply a read it cannot support.
        line += " No quote data behind that."
    return line


def _bias(s: Bias) -> str:
    return f"Bias is {s.direction}."


def _regime(s: Regime) -> str:
    return f"The tape is {s.state}."


def _level(s: Level) -> str:
    return f"{_ANCHOR_KINDS.get(s.level_type, s.level_type).capitalize()} at {spoken_price(s.price)}."


def _alert(s: Alert) -> str:
    return s.message or s.reason


def _action(s: Action) -> str:
    # Actions are recommendations; Steve confirms before anything executes.
    # The phrasing must not sound like a report of something already done.
    return f"Suggestion: {s.verb}."


# isinstance dispatch, most specific first — the orderflow types subclass
# Signal directly, so ordering only matters if a future type subclasses another.
_PHRASINGS = (
    (SetupRecognition, _setup_recognition),
    (AbsorptionRead,   _absorption_read),
    (SweepPrint,       _sweep_print),
    (DeltaDivergence,  _delta_divergence),
    (ImbalanceStack,   _imbalance_stack),
    (Bias,             _bias),
    (Regime,           _regime),
    (Level,            _level),
    (Alert,            _alert),
    (Action,           _action),
)


def speak(sig: Signal) -> str | None:
    """Render one Signal as a sentence meant to be heard.

    Returns ``None`` when there is no phrasing for this type. That is a
    deliberate refusal, not a failure: an unrecognised signal is left silent
    rather than narrated from its ``reason`` field, because ``reason`` is
    harness vocabulary and speaking it is the exact failure st-v95 recorded.
    """
    for cls, phrasing in _PHRASINGS:
        if isinstance(sig, cls):
            line = phrasing(sig)
            _assert_live(line, sig)
            return line

    log.debug(
        "speech: no phrasing for %s from %s — staying silent",
        type(sig).__name__, getattr(sig, "source", "?"),
    )
    return None


def _assert_live(line: str, sig: Signal) -> None:
    lowered = line.lower()
    for token in _HINDSIGHT_TOKENS:
        if token in lowered:
            raise HindsightLeak(
                f"{type(sig).__name__} phrasing would speak the HINDSIGHT term "
                f"{token!r} in real time: {line!r}"
            )
