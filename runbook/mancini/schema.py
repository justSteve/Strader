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

# Typed level fields [st-9r51, Stage 1]. `label` stays as written for display;
# these are what a sentinel can branch on without parsing prose. Each is a
# CLOSED vocabulary enforced by validate.check(), and each has a value meaning
# "the letter did not say" — absence is a real answer, not a gap to fill by
# guessing.

# Does Mancini want this level traded?
#   trade   — he would take it here
#   offered — he names it as an entry but does not take it himself. Load-bearing
#             and not in the 08-13 plan's three values: he gives short entries
#             every letter while saying "I have not had a single short in over a
#             year". Calling those `trade` misreports him and `avoid` discards
#             a level he deliberately published.
#   watch   — a marker, target or boundary, not an entry
#   avoid   — he says outright he will not touch it (3.9% of rich callouts)
#   unstated — no intent language
LEVEL_INTENTS = ("trade", "offered", "watch", "avoid", "unstated")

# His confidence in his OWN words, bucketed. The plan proposed a `hostile`
# value; dropped, because measured against the corpus every candidate for it
# ("I won't touch it", "totally used up") is already intent=avoid plus
# conviction=low, and a fourth bucket that never fires on its own is dead weight.
LEVEL_CONVICTIONS = ("high", "medium", "low", "unstated")

# The setup type he names at the level. Frequencies over 229 rich callouts from
# the last 20 parses, which is what these values are drawn from rather than
# guessed: failed_breakdown 20.1%, breakout_target 15.7%, level_reclaim 8.3%,
# backtest_long 7.9%, breakdown_short 6.6%, bid_direct 3.5%.
#
# `level_reclaim` and `bid_direct` are additions to the 08-13 plan's list.
# Reclaim is one of Mancini's two named trigger events ("Failed Breakdown or
# Level Reclaim") and appears in 8.3% of callouts; omitting it would have forced
# every reclaim into `none`. `bid_direct` is the name of his own section.
LEVEL_SETUPS = ("failed_breakdown", "level_reclaim", "breakdown_short",
                "backtest_long", "breakout_target", "bid_direct", "none")

# Commentary tags, closed [st-9r51]. The open vocabulary reached 83 distinct
# values across the store, including failed_breakdown (56) beside
# failed-breakdown (13), bull_case (77) beside bull-case (5), and eight
# spellings of "short". A field nothing validates is worse than no field,
# because a consumer branches on it and silently misses the day it is spelled
# differently. Section provenance, actionability, setup (same vocabulary as
# LEVEL_SETUPS), and context.
COMMENTARY_TAGS = (
    "bull_case", "bear_case", "summary",
    "long_entry", "short_entry", "no_entry",
    "failed_breakdown", "level_reclaim", "breakdown_short",
    "backtest_long", "breakout_target", "bid_direct",
    "regime", "risk", "runner", "catalyst", "structure",
)

# Variant spellings seen in the store, mapped to the canonical tag. Applied by
# normalize_tags() so the history and a slip of the hyphen both land in the
# closed vocabulary instead of being dropped.
_TAG_ALIASES = {
    "failed-breakdown": "failed_breakdown", "bull-case": "bull_case",
    "bear-case": "bear_case", "in_summary": "summary", "lean": "summary",
    "breakdown": "breakdown_short", "short": "short_entry",
    "shorts": "short_entry", "short_entries": "short_entry",
    "short_setup": "short_entry", "short_side": "short_entry",
    "short_zone": "short_entry", "short_levels": "short_entry",
    "long": "long_entry", "long_setup": "long_entry", "entry": "long_entry",
    "entry_zone": "long_entry", "no_trade": "no_entry",
    "no_engage": "no_entry", "avoid": "no_entry",
    "target": "breakout_target", "targets": "breakout_target",
    "breakout": "breakout_target", "backtest": "backtest_long",
    "caution": "risk", "risk_note": "risk", "advanced": "risk",
    "position": "runner", "positioning": "runner",
    "range": "structure", "flag": "structure", "range-boundary": "structure",
}


def normalize_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    """``(canonical, unknown)`` — fold variants, report what did not map.

    Unknown tags are RETURNED, not raised on and not silently dropped: they are
    reported by the run so the vocabulary can grow deliberately, while a bad tag
    never costs the session its levels.
    """
    canon: list[str] = []
    unknown: list[str] = []
    for t in tags:
        key = str(t).strip().lower()
        key = _TAG_ALIASES.get(key, key)
        if key in COMMENTARY_TAGS:
            if key not in canon:
                canon.append(key)
        elif key:
            unknown.append(str(t))
    return canon, unknown

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
    # Typed, branchable versions of what `label` says in prose [st-9r51].
    # Closed vocabularies above; the extractor sets these, validate enforces
    # them. Defaults are the "letter did not say" values, so a parse written
    # before these existed reads as unstated rather than as a false claim.
    intent: str = "unstated"      # one of LEVEL_INTENTS
    conviction: str = "unstated"  # one of LEVEL_CONVICTIONS
    setup: str = "none"           # one of LEVEL_SETUPS

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
            intent=str(d.get("intent") or "unstated"),
            conviction=str(d.get("conviction") or "unstated"),
            setup=str(d.get("setup") or "none"),
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
