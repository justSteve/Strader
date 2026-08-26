"""Emission rendering — strings built from the lexicon, never by hand. [st-bkvt]

``renderer.py`` consumes ``docs/lexicon/lexicon.yaml``'s ``emission:`` block
and derives the spoken surface's liveness guard from its ``live:`` stamps;
``numbers.py`` holds the number-to-words helpers the spoken surface needs and
the presentation layer re-exports.
"""
from market.emission.numbers import spoken_count, spoken_price
from market.emission.renderer import (
    EmissionError,
    HindsightLeak,
    SchemaError,
    SlotError,
    reload,
    render,
    renders,
    schema,
)

__all__ = [
    "render", "renders", "schema", "reload",
    "EmissionError", "SchemaError", "SlotError", "HindsightLeak",
    "spoken_count", "spoken_price",
]
