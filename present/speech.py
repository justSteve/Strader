"""Render emitted Signals as sentences meant to be *heard*.

``present/signals.py`` formats the same objects for the eye — a tmux pane you
scan. This module is its ear-side twin, and it is deliberately a separate
rendering rather than a reuse of ``Signal.reason``:

1. ``reason`` is written to be read, in measurement-harness vocabulary.
   ``docs/training/plain-words-glossary.md`` (st-v95) exists precisely because
   that vocabulary reached Steve undefined, and every word chosen here comes
   from it. The glossary is not itself the authority: it is the plain-words
   rendering of ``docs/lexicon/lexicon.yaml``, which is (Strader ruling
   2026-08-25, st-hmbr, finding 12 of the emission vocabulary review). On any
   disagreement the lexicon wins and the glossary is corrected.
2. Prices must be spoken the way a trader says them. "7438.25" read literally
   is "seven thousand four hundred thirty eight point two five" — wrong idiom,
   and too slow to be useful while the tape is moving.
3. LIVE vs HINDSIGHT is a safety property. Percentiles, cells, legs and
   archetypes are computable only once the day completes; speaking one in real
   time asserts something unknowable, so :func:`speak` refuses to emit them at
   all. The stamp is the lexicon's per-term ``live:`` field and the refusal is
   DERIVED from it — :func:`market.emission.renderer.assert_speakable`, which
   refuses anything not stamped exactly ``live``. This module carried a
   hand-copied list of 13 tokens until 2026-08-26; it covered 10 of 27
   hindsight terms and could not be completed in principle, because a
   substring denylist cannot tell ``leg`` from *allege*. Desk Ruling 8
   retired it rather than extending it. [st-hd51]

4. Vocabulary is not written here either, for the emissions that have moved
   so far — one, ``sweep-print``. It renders through
   ``market/emission/renderer.py`` from the lexicon's ``emission:`` block, so the
   word naming a quantity is necessarily the same word the written line uses:
   neither surface contains it. The spoken line used to say "eight ticks"
   while the log said "3 levels", for one field the lexicon had already named
   tick-level — st-bkvt, Desk Ruling 1 item 5. Every phrasing below that still
   builds its own string is the un-migrated remainder, each on its own bead
   (``_imbalance_stack`` on st-iq9g, and see the note there for why partial
   migration of a single emission is worse than none).

Scope: a pure function, ``Signal -> str | None``. ``None`` means "no phrasing
for this", never a guess. What is *worth* saying, how utterances queue, what
gets dropped when speech falls behind the tape, and the reader process itself
are all separate concerns and separate beads.

Bead: st-mhkp. Audio substrate proven under COO co-fsg5p.
"""
from __future__ import annotations

import logging

# spoken_price/spoken_count live in market/emission/numbers.py so the market
# layer can reach them without importing the presentation layer. Re-exported
# here: this module was their home and strader/intent/readback.py imports them
# from it. [st-bkvt]
# ``render`` is the function and ``renderer`` is the module. They are imported
# under their own names deliberately: `from market.emission import render` used
# to resolve to whichever the import machinery had bound last, and aliasing the
# module over the function is a TypeError one call site away. [st-hd51]
from market.emission import render, renderer
from market.emission.numbers import spoken_count, spoken_price
# One HindsightLeak, not two. The schema-rendered path and the hand-built
# phrasings below fail the same way with the same class, so a caller guarding
# against a hindsight leak does not have to know which half produced it.
# Re-exported here because this module was its home. [st-hd51]
from market.emission.renderer import HindsightLeak
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
    return render("sweep-print", "speech", {
        "direction": s.direction,
        "ticks_swept": s.ticks_swept,
        "end_price": s.end_price,
        "total_size": s.total_size,
    })


def _delta_divergence(s: DeltaDivergence) -> str:
    extreme = "high" if s.kind == "bearish" else "low"
    return (
        f"Divergence at {spoken_price(s.price_extreme)}. "
        f"New {extreme}, but the aggression did not follow."
    )


def _imbalance_stack(s: ImbalanceStack) -> str:
    # NOT YET RENDERED FROM THE SCHEMA, deliberately. The bare "levels" here is
    # the second half of the review's finding 2 and its replacement word,
    # ladder-rung, is already declared in the lexicon. But this emission's
    # WRITTEN half (market/orderflow/imbalance.py:69) hand-builds "N levels"
    # too, and moving only the spoken half would leave one field with two
    # words across two surfaces — the exact defect st-bkvt exists to end,
    # recreated one file over. Both halves migrate together on st-iq9g.
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
    """Refuse to speak anything the lexicon does not stamp exactly ``live``.

    The net exists because no LIVE signal type below carries a hindsight
    quantity today — it is here so a future phrasing, or a subclass someone
    adds in a hurry, cannot start narrating one by accident. What it refuses
    is derived from ``docs/lexicon/lexicon.yaml`` at
    :func:`market.emission.renderer.unspeakable`, never listed here: a term
    added to the lexicon is covered the day it lands, and this module has no
    copy of the vocabulary to fall out of date. [st-hd51, Desk Ruling 8]
    """
    renderer.assert_speakable(line, f"{type(sig).__name__} phrasing")
