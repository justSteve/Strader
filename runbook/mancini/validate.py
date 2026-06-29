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

from .schema import ParseResult, LEVEL_KINDS, TRIGGER_TYPES


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
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


def _appears_in_source(price: float, source: str) -> bool:
    """True if any rendering of ``price`` appears as a standalone number.

    Word boundaries prevent 581 matching inside 5812. Commas and decimals are
    handled by checking the literal rendering with boundary-aware regex.
    """
    for rendering in _price_renderings(price):
        # Escape regex metacharacters in the rendering (the "." and ",").
        pat = re.escape(rendering)
        # A "standalone" number is one not flanked by other digits. We allow it
        # to be flanked by a decimal point/comma only as part of the rendering
        # itself (already in `pat`).
        if re.search(rf"(?<!\d){pat}(?!\d)", source):
            return True
    return False


def check(raw_text: str, result: ParseResult) -> ValidationResult:
    """Validate a ParseResult against the raw newsletter it came from."""
    errors: list[str] = []
    missing: list[float] = []

    if not raw_text or not raw_text.strip():
        return ValidationResult(ok=False, errors=["empty source text"])

    # Schema-level sanity: enum membership.
    for i, lvl in enumerate(result.levels):
        if lvl.kind not in LEVEL_KINDS:
            errors.append(f"level[{i}] has invalid kind {lvl.kind!r}")
    for i, c in enumerate(result.commentary):
        if c.trigger.type not in TRIGGER_TYPES:
            errors.append(
                f"commentary[{i}] trigger has invalid type {c.trigger.type!r}"
            )

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

    return ValidationResult(ok=not errors, errors=errors, missing_prices=missing)
