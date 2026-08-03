"""FD0 execution harness — compose, derive, render. Never transmit.

Layer-1 by construction: no order API, no credentials, no transmission. FD0
renders a ticket and an order string for Steve to paste into TOS himself. The
wall between authoring trade code and executing it is st-5ey's, and nothing in
this package crosses it.

Design: ``docs/superpowers/specs/2026-08-02-fd0-flushdown-design.md``.
Bead: Cut And Await (st-apzt).
"""

from strader.execution.compose import (
    Budget,
    CannotFund,
    Contract,
    Derivation,
    NoStrikeInBand,
    Ticket,
    compose,
    derive,
    noise_floor_spx,
    order_string,
    parse_chain,
    pick_strike,
    template_fields,
)

__all__ = [
    "Budget",
    "CannotFund",
    "Contract",
    "Derivation",
    "NoStrikeInBand",
    "Ticket",
    "compose",
    "derive",
    "noise_floor_spx",
    "order_string",
    "parse_chain",
    "pick_strike",
    "template_fields",
]
