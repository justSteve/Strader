"""Which words in a level callout are Mancini's, and which are the extractor's.

[st-9r51] `schema.callout()` gives the text that turns "price near 7745" into an
actionable alert. What it cannot say is whether that text is a **quotation** or
the extractor's own **gloss** — and the sentinel needs to know before it puts
words in Mancini's mouth. `validate.check()` never covered this: it requires
every PRICE to appear verbatim in the letter and says nothing about prose. The
08-13 plan measured the consequence directly — "very weak, shaky", "I won't
touch it" and "heavily used up now and risky to just buy directly" are all
verbatim Mancini, while "the preferred entry" has ZERO occurrences in the letter
it was attached to, and nothing marked the difference.

**Why this is spans and not a boolean.** The plan specified `callout_verbatim`
as a bool. Measured over 269 real callouts across 26 parses, the whole callout
is a contiguous quote in **4 of them (1%)** — a bool would be False almost
always and carry no information. Callouts are composites: Mancini's phrase
stitched into connective tissue, median longest quoted run 33% of the callout.
So the useful unit is the span. The sentinel quotes the spans and renders the
rest unattributed.

Everything here is deterministic string work — no model, no spend.
"""
from __future__ import annotations

import re

# Same-length character folds only, so token offsets stay valid against the
# ORIGINAL string and a matched span can be sliced back out of it for display.
_FOLD = str.maketrans({
    "’": "'", "‘": "'",      # curly single quotes
    "“": '"', "”": '"',      # curly double quotes
    "—": "-", "–": "-",      # em/en dash
    "·": "-",                     # the label's major separator
    " ": " ",                     # nbsp
})

_WORD_RE = re.compile(r"[a-z0-9]+")

# A run shorter than this is coincidental overlap, not a quotation worth
# attributing. Measured across the 269-callout corpus: at 4 words the split is
# 49% gloss / 51% mixed, which is where the field discriminates best. Short
# boilerplate runs ("the low of day") scoring as quotation is harmless — they
# ARE Mancini's words. The risk this field exists to catch is the opposite one,
# an invented characterisation, and that scores gloss at any threshold.
DEFAULT_MIN_WORDS = 4

# callout_attribution values. A closed vocabulary, like schema.LEVEL_KINDS.
ATTR_QUOTED = "quoted"    # the whole callout is one contiguous quotation
ATTR_MIXED = "mixed"      # at least one quoted span, plus extractor connective
ATTR_GLOSS = "gloss"      # no span long enough to attribute — extractor's words
ATTR_NONE = ""            # no callout to attribute (not "gloss": nothing said)
ATTRIBUTIONS = (ATTR_QUOTED, ATTR_MIXED, ATTR_GLOSS, ATTR_NONE)


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.translate(_FOLD).lower())


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """``(word, start, end)`` over the original string, offsets preserved."""
    folded = text.translate(_FOLD).lower()
    return [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(folded)]


def haystack(source: str) -> str:
    """The letter as a space-delimited word stream, padded for run matching.

    Padding with a leading and trailing space is what makes ``" a b c " in hay``
    a word-boundary test rather than a substring test — without it "own" would
    match inside "known".
    """
    return " " + " ".join(_words(source)) + " "


def quoted_spans(text: str, source: str, min_words: int = DEFAULT_MIN_WORDS,
                 hay: str | None = None) -> list[str]:
    """The maximal runs of ``text`` that appear verbatim in ``source``.

    Returned as slices of the ORIGINAL ``text`` — original casing and internal
    punctuation — so a caller can render them as quotations. Runs are found
    greedily left to right and never overlap: at each position the longest run
    that matches wins, and scanning resumes after it.

    ``hay`` lets a caller hoist ``haystack(source)`` out of a loop over many
    levels; it is an optimisation only and must be built from the same source.
    """
    if not text.strip():
        return []
    if hay is None:
        hay = haystack(source)
    toks = _tokens(text)
    n = len(toks)
    words = [t[0] for t in toks]

    spans: list[str] = []
    i = 0
    while i < n:
        j = n
        while j > i:
            if " " + " ".join(words[i:j]) + " " in hay:
                break
            j -= 1
        if j - i >= min_words:
            spans.append(text[toks[i][1]:toks[j - 1][2]])
            i = j
        else:
            i += 1
    return spans


def classify(text: str, spans: list[str]) -> str:
    """One of ``ATTRIBUTIONS``, given a callout and its quoted spans.

    ``quoted`` is reserved for a callout that is ONE span covering every word —
    a two-span callout is mixed even if the spans happen to cover it all, since
    the extractor still chose the join.
    """
    if not text.strip():
        return ATTR_NONE
    if not spans:
        return ATTR_GLOSS
    if len(spans) == 1 and _words(spans[0]) == _words(text):
        return ATTR_QUOTED
    return ATTR_MIXED


def annotate(levels, source: str, min_words: int = DEFAULT_MIN_WORDS) -> None:
    """Fill ``callout_quotes`` / ``callout_attribution`` on ``levels``, in place.

    Called once per run with the cleaned letter, after validation passes. Levels
    whose label is bare ``major`` (or empty) carry no callout and come out as
    ``ATTR_NONE`` with no spans.
    """
    from .schema import callout as _callout

    hay = haystack(source)
    for lv in levels:
        text = _callout(getattr(lv, "label", ""))
        spans = quoted_spans(text, source, min_words=min_words, hay=hay)
        lv.callout_quotes = spans
        lv.callout_attribution = classify(text, spans)
