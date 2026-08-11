"""Mancini daily chart generation (deterministic). [co-t1z9]

The #3 feasibility verdict (spec addendum 2026-06-29): LuxAlgo Quant prompt
delivery is NOT automatable, but loading a Pine script and overlaying exact
horizontal levels IS — via tradingview-mcp (pine_set_source / draw_shape). So
the Mancini *daily* chart is produced deterministically here, bypassing Quant:

    validated ParseResult  -> to_mancini_email()  -> mancini.pine_emitter.emit()
                                                   -> apply_plan()  (pine + per-line specs)

This REUSES the existing, sophisticated `mancini/pine_emitter.py` (Pine v6 with
runtime visibility toggles and key-level highlighting) rather than duplicating
Pine generation. The only new logic is the bridge from the LLM ParseResult to
the emitter's ManciniEmail input — and the meaningful mapping that a level is
"key" if Mancini cites its price in his forward-looking commentary.

Quant stays a manual, occasional path for authoring a strat's chart *scaffold*;
the per-strat Quant prompt remains a version-controlled asset + TV-reset recovery
recipe, surfaced (not auto-delivered) by the Runbook.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

# Absolute imports resolve to Strader's top-level packages (not runbook.mancini).
from mancini.parser import ManciniEmail, Level as RegexLevel
from mancini.pine_emitter import emit as emit_pine_source

from . import schema
from .schema import ParseResult
from .validate import split_out_of_band

logger = logging.getLogger(__name__)


def _sane_result(result: ParseResult) -> ParseResult:
    """Drop out-of-band levels (letter typos) before any chart emit. [st-wqr]"""
    sane, dropped = split_out_of_band(result.levels)
    for lv in dropped:
        logger.warning("SANITY: level %s (%s, %r) outside session band — "
                       "dropped from chart emit; letter likely has a typo",
                       lv.price, lv.kind, lv.source_quote)
    return dataclasses.replace(result, levels=sane) if dropped else result


def _is_major(label: str) -> bool:
    """Delegates to the shared rule; see schema.is_major. [st-eo0]"""
    return schema.is_major(label)


def key_prices(result: ParseResult) -> set[float]:
    """Prices Mancini cites in forward-looking commentary = 'key' levels.

    Maps the LLM commentary's anchor_prices onto the emitter's key-level concept:
    a published level that also shows up in his bull/bear-case discussion renders
    opaque/always-on, exactly the emitter's intent.
    """
    keys: set[float] = set()
    for c in result.commentary:
        for p in c.trigger.anchor_prices:
            keys.add(float(p))
    return keys


def to_mancini_email(result: ParseResult) -> ManciniEmail:
    """Bridge a validated ParseResult to the pine_emitter's ManciniEmail input.

    Maps support/resistance kinds to the emitter's two arrays. ``label``
    containing 'major' sets the major tier. ``key_levels`` are the
    commentary-cited prices. pivot/target/trigger kinds are carried as key
    levels so they render when they coincide with a drawn level; a dedicated
    array for them is a documented follow-up (the emitter only draws S/R today).
    """
    keys = key_prices(result)
    supports: list[RegexLevel] = []
    resistances: list[RegexLevel] = []

    for lvl in result.levels:
        annotation = "major" if _is_major(lvl.label) else ""
        rl = RegexLevel(price=float(lvl.price), annotation=annotation)
        if lvl.kind == "support":
            supports.append(rl)
        elif lvl.kind == "resistance":
            resistances.append(rl)
        else:
            # pivot/target/trigger — mark as key so they always render if they
            # also appear in an S/R array; and record the price as key.
            keys.add(float(lvl.price))

    return ManciniEmail(
        date=result.date,
        subject=f"Mancini {result.instrument} {result.date}".strip(),
        support_levels=supports,
        resistance_levels=resistances,
        key_levels=sorted(keys),
    )


def emit_pine(result: ParseResult, *, generated_at: str = "") -> str:
    """Render Pine v6 overlay source for the day's validated levels."""
    return emit_pine_source(
        to_mancini_email(_sane_result(result)),
        generated_at=generated_at or None,
    )


def apply_plan(result: ParseResult, *, generated_at: str = "") -> dict[str, Any]:
    """A delivery-agnostic plan for tradingview-mcp.

    Carries both delivery paths the verdict confirmed possible:
      - ``pine_source``: hand to tradingview-mcp ``pine_set_source`` + ``pine_smart_compile``.
      - ``lines``: per-level specs for ``draw_shape`` horizontal_line at exact price.
    The Runbook (or a thin tradingview-mcp client) consumes whichever is wired.
    """
    result = _sane_result(result)
    keys = key_prices(result)
    lines = [
        {
            "price": float(lvl.price),
            "kind": lvl.kind,
            "label": lvl.label,
            "is_key": float(lvl.price) in keys,
        }
        for lvl in result.levels
    ]
    return {
        "instrument": result.instrument,
        "date": result.date,
        "pine_source": emit_pine(result, generated_at=generated_at),
        "lines": lines,
    }
