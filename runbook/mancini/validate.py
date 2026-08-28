"""Validation for parsed Mancini output. [co-7lyf]

The headline check is **anti-hallucination**: this is financial data, and an LLM
asked to extract levels can fabricate a plausible-but-wrong number. So every
numeric price the model returns — both ``Level.price`` and each
``Trigger.anchor_prices`` entry — must literally appear in the raw newsletter
text. Any price that does not is rejected; the caller then keeps yesterday's
last-good artifacts rather than publishing suspect levels.

This is a pure function over (raw_text, ParseResult). It does not call the LLM
and has no I/O, so it is cheap to unit-test with a poisoned fixture.

Design ref: spec section 7.4 ("no hallucinated numbers"); partner of the
enterprise no-confabulation rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import (ParseResult, LEVEL_KINDS, TRIGGER_TYPES, LEVEL_INTENTS,
                     LEVEL_CONVICTIONS, LEVEL_SETUPS, normalize_tags)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    # Tags outside COMMENTARY_TAGS that could not be folded to a canonical
    # one. Reported, never fatal — see the tag handling in check(). [st-9r51]
    unknown_tags: list[str] = field(default_factory=list)
    # Prices that could not be found verbatim in the source, for diagnostics.
    missing_prices: list[float] = field(default_factory=list)


def _price_renderings(price: float) -> list[str]:
    """Every plausible string form a price could take in the newsletter.

    Mancini writes ES levels variously: "5812", "5812.5", "5812.50",
    "5,812". A price matches the source if ANY of these renderings appears.
    """
    renderings: set[str] = set()
    # Integer form when the price is whole-valued (5812.0 -> "5812").
    if float(price).is_integer():
        as_int = str(int(round(price)))
        renderings.add(as_int)
        # thousands-separated, e.g. "5,812"
        renderings.add(f"{int(round(price)):,}")
    # One- and two-decimal forms.
    renderings.add(f"{price:.1f}")
    renderings.add(f"{price:.2f}")
    # Trim a trailing ".0"/".00" that f-string may produce redundantly.
    trimmed = f"{price}".rstrip("0").rstrip(".") if "." in f"{price}" else f"{price}"
    renderings.add(trimmed)
    return [r for r in renderings if r]


# Zone shorthand, e.g. "7725-30" — Mancini's way of naming a two-edged level.
# listlevels._expand_zone already reads both edges out of it; this regex lets
# the validator see the same thing. [st-f3at]
_ZONE_RE = re.compile(r"(?<!\d)(\d{3,5})-(\d{1,4})(?!\d)")


def _zone_edges(source: str) -> set[float]:
    """Every price written in the source as an edge of a zone shorthand.

    "7725-30" names 7725 AND 7730, but only the first is a standalone digit run,
    so ``_appears_in_source`` alone would call the second a hallucination. It is
    not — the letter said it, in Mancini's shorthand. Expansion is deliberately
    identical to ``listlevels._expand_zone`` (suffix replaces the base's trailing
    digits); anything else and the deterministic scrape and this check would
    disagree about what the letter contains, which is the deadlock this fixes.
    """
    edges: set[float] = set()
    for base, suffix in _ZONE_RE.findall(source):
        if len(suffix) >= len(base):
            continue  # not a zone: "2026-2027", a date range, an em-dash span
        edges.add(float(base))
        edges.add(float(base[: len(base) - len(suffix)] + suffix))
    return edges


def _appears_in_source(price: float, source: str) -> bool:
    """True if any rendering of ``price`` appears as a standalone number.

    Word boundaries prevent 581 matching inside 5812. Commas and decimals are
    handled by checking the literal rendering with boundary-aware regex. A price
    also counts as written when it is an edge of a zone shorthand ("7725-30").
    """
    for rendering in _price_renderings(price):
        # Escape regex metacharacters in the rendering (the "." and ",").
        pat = re.escape(rendering)
        # A "standalone" number is one not flanked by other digits. We allow it
        # to be flanked by a decimal point/comma only as part of the rendering
        # itself (already in `pat`).
        if re.search(rf"(?<!\d){pat}(?!\d)", source):
            return True
    return price in _zone_edges(source)


def check(raw_text: str, result: ParseResult) -> ValidationResult:
    """Validate a ParseResult against the raw newsletter it came from."""
    errors: list[str] = []
    missing: list[float] = []
    unknown_tags: list[str] = []

    if not raw_text or not raw_text.strip():
        return ValidationResult(ok=False, errors=["empty source text"])

    # Schema-level sanity: enum membership.
    for i, lvl in enumerate(result.levels):
        if lvl.kind not in LEVEL_KINDS:
            errors.append(f"level[{i}] has invalid kind {lvl.kind!r}")
        # Typed level fields [st-9r51]. Enforced as strictly as `kind`: these
        # are closed vocabularies the extractor writes deliberately, so a value
        # outside them means it misunderstood the contract, not that Mancini
        # said something unusual. "Did not say" has its own legal value in each.
        for fname, allowed in (("intent", LEVEL_INTENTS),
                               ("conviction", LEVEL_CONVICTIONS),
                               ("setup", LEVEL_SETUPS)):
            val = getattr(lvl, fname, None)
            if val is not None and val not in allowed:
                errors.append(
                    f"level[{i}] has invalid {fname} {val!r} "
                    f"(allowed: {', '.join(allowed)})")
    for i, c in enumerate(result.commentary):
        if c.trigger.type not in TRIGGER_TYPES:
            errors.append(
                f"commentary[{i}] trigger has invalid type {c.trigger.type!r}"
            )
        # Tags are normalised, NOT rejected. Deliberately unlike the fields
        # above: a tag is descriptive metadata, and failing validation costs
        # the session its levels fifteen minutes before the bell. An unknown
        # tag is reported so the vocabulary can grow on purpose, and the
        # canonical ones are kept.
        canon, unknown = normalize_tags(c.tags)
        c.tags = canon
        for t in unknown:
            unknown_tags.append(f"commentary[{i}]: {t!r}")

    # Anti-hallucination: every price must appear verbatim in the source.
    for i, lvl in enumerate(result.levels):
        if not _appears_in_source(lvl.price, raw_text):
            missing.append(lvl.price)
            errors.append(
                f"level[{i}] price {lvl.price} not found verbatim in source"
            )
    for i, c in enumerate(result.commentary):
        for price in c.trigger.anchor_prices:
            if not _appears_in_source(price, raw_text):
                missing.append(price)
                errors.append(
                    f"commentary[{i}] anchor price {price} not found verbatim in source"
                )

    return ValidationResult(ok=not errors, errors=errors, missing_prices=missing,
                            unknown_tags=unknown_tags)


# --- Emit-time level sanity band [st-wqr] -----------------------------------
#
# The anti-hallucination check above catches prices the MODEL invented; it
# cannot catch prices the LETTER itself got wrong. Mancini's 2026-07-30 letter
# contained 'Resistances are: 743, 7449 ...' — a dropped digit the extractor
# faithfully carried onto the chart, where a level an order of magnitude below
# the traded band stretches the renderer's price scale into uselessness.
#
# The band is relative — median of the session's own level set ± pct — so it
# needs no market-data fetch and survives regime moves. At ES ~7500 the default
# 10% band is ±~750 pts: an order-of-magnitude typo (743) or an extra digit
# (74490) falls far outside it, while Mancini's legitimately deep ladders
# (~400-500 pts) stay comfortably inside. A dropped level is a SIGNAL the
# letter has a typo: emitters log each one loudly, and the morning brief
# surfaces them — never drop silently.

SANITY_BAND_PCT = 0.10


def level_sanity_band(prices: list[float], pct: float = SANITY_BAND_PCT):
    """(lo, hi) around the median, or None when too few points to judge."""
    if len(prices) < 3:
        return None
    s = sorted(prices)
    mid = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2
    return (mid * (1 - pct), mid * (1 + pct))


def split_out_of_band(levels, pct: float = SANITY_BAND_PCT):
    """Partition levels into (kept, dropped) against the session's own band.

    ``levels`` is any sequence with a ``.price`` attribute (schema.Level).
    With fewer than 3 levels there is no meaningful median: keep everything.
    """
    band = level_sanity_band([lv.price for lv in levels], pct)
    if band is None:
        return list(levels), []
    lo, hi = band
    kept = [lv for lv in levels if lo <= lv.price <= hi]
    dropped = [lv for lv in levels if not (lo <= lv.price <= hi)]
    return kept, dropped
