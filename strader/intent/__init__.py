"""The intent dialect — Steve's spoken day-description into entities, with a spoken read-back.

Bead: Intent Dialect Parser (st-79z.3), child of the Trade Language Front (st-79z).
Design record: st-79z.2 and ``docs/superpowers/specs/2026-08-22-intent-dialect-design.md``.
Entity model: the 2026-07-25 survey (``docs/research/2026-07-25-trade-language-entity-survey.md``).

Steve, 2026-07-31: *"Instead of ticking boxes on an order editor, we can speak what we
see and have the form pre-populate."* This package is that sentence as code, built
deterministically first (Steve's harness-first rule) — a model is allowed later only as a
bounded function over genuine free text, and nothing here calls one.

Modules, in the order a day uses them:

``numbers``    spoken prices to numbers — "sixty-four twelve" is 6412, "seventy-four oh
               five" is 7405, "and a quarter" adds 0.25 — and the price frame (ES or SPX)
               that every number must carry.
``entities``   the survey's entities: Level, Trigger, Setup, Regime, SessionWindow, Intent,
               StructureTemplate, Order; and DayPlan, which holds a day's worth of them.
``grammar``    the deterministic extractor: a sentence of dictation becomes levels, a
               regime call, an intent branch or a structure — or is reported as not
               understood, never guessed at.
``readback``   the four-tier spoken read-back in trader phrasing, and the direction-anchor
               echo that every directional intent must pass.
``tos``        the TOS paste string for an Order. The single-leg shape is the one FD0
               already uses; the multi-leg shape is INFERRED until the fixture pass lands
               (TOS Order Fixtures, st-79z.5) and says so on every rendering.
``session``    the verbs — read / mark / call / arm / yes / no / fly / single / price / go /
               stand down / show — over a DayPlan that persists to disk.
``cli``        ``python -m strader.intent`` — one verb per line, read-back after each.

The wall: this package never transmits. ``go`` emits a paste string and a staged ticket
record; the execution gate (st-5ey) and the fire server's covenant are untouched.
"""
from strader.intent.entities import (  # noqa: F401
    DayPlan, Frame, Intent, Level, Order, Price, Regime, SessionWindow, Setup,
    StructureTemplate, Trigger,
)
from strader.intent.session import Session  # noqa: F401

__all__ = [
    "DayPlan", "Frame", "Intent", "Level", "Order", "Price", "Regime", "SessionWindow",
    "Setup", "StructureTemplate", "Trigger", "Session",
]
