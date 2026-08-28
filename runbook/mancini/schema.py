"""Structured schema for a parsed Mancini newsletter. [co-7lyf]

These dataclasses are the contract between the LLM extraction step (llm.py) and
everything downstream (validation, the commentary store, chart generation, the
morning brief). The same field names are used as the JSON Schema handed to the
model (see llm.TOOL_SCHEMA) so the model's tool-call output maps 1:1 onto
``ParseResult.from_dict``.

Design ref: spec section 7.2.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Allowed enum values. Kept here (not just in the JSON schema) so validation and
# tests have a single source of truth.
LEVEL_KINDS = ("support", "resistance", "pivot", "target", "trigger")
TRIGGER_TYPES = ("price_cross", "price_zone", "time", "regime", "unconditional")

# ParseResult.model values that mean "levels only, no reading of the letter":
# the old hybrid path's "deterministic-lists" and the backfill's
# "listlevels-backfill" (scripts/mancini_backfill_levels.py, co-vp45h). The
# 08:15 prepare, the hybrid skip and the overnight refresh all treat such an
# artifact as NOT a parse — the morning must still ask for the real one.
DETERMINISTIC_LISTS_MODEL = "deterministic-lists"
BACKFILL_MODEL = "listlevels-backfill"
LEVELS_ONLY_MODELS = (DETERMINISTIC_LISTS_MODEL, BACKFILL_MODEL)


def is_levels_only(model: str | None) -> bool:
    """True when ``model`` names a levels-only artifact (see LEVELS_ONLY_MODELS)."""
    return (model or "") in LEVELS_ONLY_MODELS

# Level.label carries two things at once [st-eo0]: the letter's `(major)`
# annotation and Mancini's own callout for that level ("shelf of lows from noon
# Thursday", "heavily used up now"). The convention is a `major` PREFIX,
# optionally followed by the callout after a separator:
#
#     "major"                            -> major, no callout
#     "major · shelf of lows from noon"  -> major + callout
#     "1st support down — weak, shaky"   -> callout only
#
# Detection is deliberately prefix-based, not substring-based. A callout can
# legitimately contain the word "major" ("lost the major June 11th low") and a
# substring test would silently promote that level everywhere it is consumed —
# the Pine chart, the Daily Payload, the overnight brief. Route every major
# check through is_major() so the rule has one definition.
_CALLOUT_SEPARATORS = ("·", "—", "-", ":", ",")


def is_major(label: str) -> bool:
    """True when the letter annotated this level `(major)`."""
    return (label or "").strip().lower().startswith("major")


def callout(label: str) -> str:
    """Mancini's own note for a level, with the `major` prefix stripped."""
    text = (label or "").strip()
    if not is_major(text):
        return text
    rest = text[len("major"):].lstrip()
    return rest.lstrip("".join(_CALLOUT_SEPARATORS)).strip()


@dataclass
class Level:
    """A numeric price level Mancini names for the session."""

    price: float
    kind: str  # one of LEVEL_KINDS
    label: str = ""
    source_quote: str = ""  # verbatim newsletter text this price came from
    # Which words of callout(label) are Mancini's [st-9r51]. Filled by
    # attribution.annotate() at parse time, where the letter is in hand; the
    # extractor never sets them. Absent on parses published before 2026-08-28,
    # so both default to "not computed" and every consumer must tolerate that.
    callout_quotes: list[str] = field(default_factory=list)
    callout_attribution: str = ""  # one of attribution.ATTRIBUTIONS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Level":
        return cls(
            price=float(d["price"]),
            kind=str(d.get("kind", "")),
            label=str(d.get("label", "")),
            source_quote=str(d.get("source_quote", "")),
            callout_quotes=[str(q) for q in d.get("callout_quotes", [])],
            callout_attribution=str(d.get("callout_attribution", "")),
        )


@dataclass
class Trigger:
    """When a piece of forward-looking commentary becomes relevant.

    ``anchor_prices`` lets the intraday highlighter (#10) test live price against
    the note without re-parsing prose. ``condition_text`` is the human-readable
    condition, kept for display and audit.
    """

    type: str  # one of TRIGGER_TYPES
    anchor_prices: list[float] = field(default_factory=list)
    condition_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Trigger":
        return cls(
            type=str(d.get("type", "unconditional")),
            anchor_prices=[float(p) for p in d.get("anchor_prices", [])],
            condition_text=str(d.get("condition_text", "")),
        )


@dataclass
class Commentary:
    """One forward-looking note from Mancini, annotated for later retrieval."""

    text: str
    trigger: Trigger
    tags: list[str] = field(default_factory=list)
    source_quote: str = ""  # verbatim newsletter text this note came from

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Commentary":
        return cls(
            text=str(d.get("text", "")),
            trigger=Trigger.from_dict(d.get("trigger", {}) or {}),
            tags=[str(t) for t in d.get("tags", [])],
            source_quote=str(d.get("source_quote", "")),
        )


@dataclass
class ParseResult:
    """The full validated output of parsing one newsletter."""

    date: str  # ISO date the newsletter is for, e.g. "2026-06-29"
    instrument: str  # e.g. "ES"
    session_bias: str
    levels: list[Level] = field(default_factory=list)
    commentary: list[Commentary] = field(default_factory=list)
    raw_excerpt: str = ""
    model: str = ""  # model id used for extraction
    parsed_at: str = ""  # ISO-8601 timestamp, stamped by the caller

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "instrument": self.instrument,
            "session_bias": self.session_bias,
            "levels": [lvl.to_dict() for lvl in self.levels],
            "commentary": [c.to_dict() for c in self.commentary],
            "raw_excerpt": self.raw_excerpt,
            "model": self.model,
            "parsed_at": self.parsed_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParseResult":
        return cls(
            date=str(d.get("date", "")),
            instrument=str(d.get("instrument", "")),
            session_bias=str(d.get("session_bias", "")),
            levels=[Level.from_dict(x) for x in d.get("levels", [])],
            commentary=[Commentary.from_dict(x) for x in d.get("commentary", [])],
            raw_excerpt=str(d.get("raw_excerpt", "")),
            model=str(d.get("model", "")),
            parsed_at=str(d.get("parsed_at", "")),
        )
