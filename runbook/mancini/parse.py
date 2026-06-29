"""Orchestrate Mancini extraction + validation. [co-7lyf]

parse() ties the pieces together but does no I/O of its own beyond the injected
extractor: text in -> (ParseResult, ValidationResult). The LLM call is injected
(default: llm.extract) so tests run deterministically with a stub.

The caller (run.py) decides policy: on validation failure, alert and keep
yesterday's last-good artifacts; never publish suspect levels.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import llm, validate
from .schema import ParseResult
from .validate import ValidationResult


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
    extractor: llm.Extractor | None = None,
    model: str = llm.MODEL,
    parsed_at: str = "",
) -> ParseOutcome:
    """Extract structured data from a newsletter and validate it.

    ``extractor`` is a callable ``(raw_text) -> dict`` (the tool-input dict). The
    default binds to the live Claude call; tests pass a stub.
    """
    extract_fn = extractor or (lambda text: llm.extract(text, model=model))

    raw = extract_fn(raw_text)
    result = ParseResult.from_dict(raw)
    # The model does not set these; the harness stamps them.
    result.model = model
    result.parsed_at = parsed_at
    if not result.raw_excerpt:
        result.raw_excerpt = raw_text[:2000]

    validation = validate.check(raw_text, result)
    return ParseOutcome(result=result, validation=validation)
