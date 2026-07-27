"""Daily payload emitter for the stable Mancini Forecast renderer. [st-5rc]

Renders a ParseResult into the v1 line-based payload the Pine renderer's
input.text_area consumes (spec: 2026-07-25-mancini-stable-renderer-design.md).

Format:
    v1 <date> <symbol>
    S|R <price> <price2|.> <major|minor> [key] [conf] ["note"]
    P poc|vah|val|lvn|hvn <price>

Only ladder levels (kind support/resistance) become S/R lines; kind='trigger'
extras remain commentary-side. Prices render trailing-zero-free (7458, 7461.5).
"""
from __future__ import annotations

from typing import Sequence

from .chart import key_prices
from .schema import Level, ParseResult

CONFLUENCE_TOLERANCE_PTS = 2.0
_PROFILE_KINDS = ("poc", "vah", "val", "lvn", "hvn")


def _fmt(price: float) -> str:
    return f"{price:g}"


def _tier(level: Level) -> str:
    return "major" if "major" in (level.label or "").lower() else "minor"


def build_payload(result: ParseResult,
                  profile_levels: Sequence[tuple[str, float]] = (),
                  *, confluence_tol: float = CONFLUENCE_TOLERANCE_PTS) -> str:
    lines = [f"v1 {result.date} {result.instrument}"]
    for lv in result.levels:
        if lv.kind == "support":
            prefix = "S"
        elif lv.kind == "resistance":
            prefix = "R"
        else:
            continue
        lines.append(f"{prefix} {_fmt(lv.price)} . {_tier(lv)}")
    return "\n".join(lines)
