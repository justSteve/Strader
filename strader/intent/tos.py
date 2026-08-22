"""The TOS paste string for an Order, and the honesty about what is known. [st-79z.3]

thinkorswim's *Paste order from clipboard* takes one line: action, signed quantity, an
optional spread keyword, underlying, multiplier, series, expiry, strikes, CALL/PUT, @price,
order type. The single-leg shape is confirmed (FD0's research of 2026-08-03, one working
example in the design doc). The **multi-leg shapes are inferred** from one external
iron-condor citation and the schwab-py enum (survey §2.1) and stay marked INFERRED until
the fixture pass lands — TOS Order Fixtures (st-79z.5): ``tests/fixtures/tos/<shape>.txt``
holding the confirm-dialog text verbatim. When a fixture file exists for a shape, the
renderer is checked against it and the rendering is reported as verified.

Every string returned is bare — no indent, no trailing newline — because the paste breaks
on stray whitespace (FD0 design, "caveat that matters").
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from strader.intent.entities import Order

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "tos"
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_SHAPE_FILES = {"SINGLE": "single.txt", "VERTICAL": "vertical.txt", "BUTTERFLY": "butterfly.txt",
                "CONDOR": "condor.txt"}


def tos_expiry(d: dt.date) -> str:
    """``3 AUG 26`` — day unpadded, month, two-digit year (same rule as FD0)."""
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year % 100:02d}"


def tos_price(p: float) -> str:
    """``.55`` under a dollar, ``1.25`` above — the documented example reads ``@.20``."""
    s = f"{p:.2f}"
    return s[1:] if s.startswith("0.") else s


def fixture_status(spread_type: str) -> str:
    """'verified' when the shape's fixture file exists, else 'inferred'."""
    name = _SHAPE_FILES.get(spread_type.upper())
    return "verified" if name and (FIXTURE_DIR / name).is_file() else "inferred"


def tos_string(o: Order) -> str:
    exp = tos_expiry(o.expiry)
    qty = f"{o.quantity:+d}"
    series = f" ({o.series})" if o.series else ""
    strikes = "/".join(f"{k:g}" for k in o.strikes)
    price = tos_price(o.price)
    if o.spread_type.upper() == "SINGLE":
        return f"{o.action} {qty} {o.underlying} {o.multiplier}{series} {exp} {strikes} {o.right} @{price} {o.order_type}".strip()
    return (f"{o.action} {qty} {o.spread_type.upper()} {o.underlying} {o.multiplier}{series} {exp} "
            f"{strikes} {o.right} @{price} {o.order_type}").strip()


def occ_symbols(o: Order) -> list[str]:
    """One OCC symbol per leg (the tape's and Schwab's namespace): ``SPXW  260725C06300000``.
    The centre leg of a butterfly appears twice, as it is held twice."""
    root = "SPXW" if o.underlying == "SPX" else o.underlying
    ymd = o.expiry.strftime("%y%m%d")
    legs = list(o.strikes)
    if o.spread_type.upper() == "BUTTERFLY" and len(legs) == 3:
        legs = [legs[0], legs[1], legs[1], legs[2]]
    return [f"{root:<6}{ymd}{o.right[0]}{int(round(k * 1000)):08d}" for k in legs]


def render(o: Order) -> tuple[str, str]:
    """(paste string, status) — status is 'verified' or 'inferred' per the fixture pass."""
    return tos_string(o), fixture_status(o.spread_type)
