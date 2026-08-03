"""Orchestrate Mancini extraction + validation. [co-7lyf]

parse() ties the pieces together but does no I/O of its own: text in ->
(ParseResult, ValidationResult). The extractor is always injected — there is no
default and no network call. Production passes a lambda closing over the
in-session extraction JSON (see extraction-contract.md); tests pass a stub.

The caller (run.py) decides policy: on validation failure, alert and keep
yesterday's last-good artifacts; never publish suspect levels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import validate
from .schema import ParseResult
from .validate import ValidationResult

#: An extractor maps raw newsletter text -> the extraction dict described in
#: extraction-contract.md. In production it simply returns the JSON an agent
#: wrote after reading the letter; the text argument is there so tests and any
#: future text-driven extractor share one signature.
Extractor = Callable[[str], dict[str, Any]]

#: Stamped onto the ParseResult when the caller supplies no more specific label.
DEFAULT_MODEL = "in-session"


@dataclass
class ParseOutcome:
    result: ParseResult
    validation: ValidationResult

    @property
    def ok(self) -> bool:
        return self.validation.ok


def parse(
    raw_text: str,
    *,
    extractor: Extractor,
    model: str = DEFAULT_MODEL,
    parsed_at: str = "",
) -> ParseOutcome:
    """Validate an extraction against the newsletter it claims to come from.

    ``extractor`` is a callable ``(raw_text) -> dict`` returning the extraction
    dict. It is required: the interpretive leg is an in-session prompt parse, so
    there is nothing sensible to fall back to when no extraction was supplied.
    """
    raw = extractor(raw_text)
    result = ParseResult.from_dict(raw)
    # The extractor does not set these; the harness stamps them.
    result.model = model
    result.parsed_at = parsed_at
    if not result.raw_excerpt:
        result.raw_excerpt = raw_text[:2000]

    validation = validate.check(raw_text, result)
    return ParseOutcome(result=result, validation=validation)
