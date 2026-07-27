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


def _note_for(price: float, result: ParseResult) -> str | None:
    """First sentence (<=60 chars) of the first commentary anchored on price."""
    for c in result.commentary:
        anchors = getattr(c.trigger, "anchor_prices", None) or []
        if any(abs(a - price) < 1e-9 for a in anchors):
            sentence = c.text.split(". ")[0].strip().rstrip(".")
            return (sentence[:57] + "...") if len(sentence) > 60 else sentence
    return None


def build_payload(result: ParseResult,
                  profile_levels: Sequence[tuple[str, float]] = (),
                  *, confluence_tol: float = CONFLUENCE_TOLERANCE_PTS) -> str:
    keys = key_prices(result)
    prof_prices = [p for k, p in profile_levels if k in _PROFILE_KINDS]

    # Zone pairing: ladder levels sharing (kind, source_quote) in pairs are the
    # two edges the extractor expanded from one "7640-45" token.
    groups: dict[tuple[str, str], list[Level]] = {}
    ordered: list[tuple[str, str]] = []
    for lv in result.levels:
        if lv.kind not in ("support", "resistance"):
            continue
        gk = (lv.kind, lv.source_quote or f"__solo_{_fmt(lv.price)}")
        if gk not in groups:
            groups[gk] = []
            ordered.append(gk)
        groups[gk].append(lv)

    lines = [f"v1 {result.date} {result.instrument}"]
    for gk in ordered:
        members = sorted(groups[gk], key=lambda l: l.price)
        first = members[0]
        prefix = "S" if first.kind == "support" else "R"
        if len(members) == 2:
            p1, p2 = _fmt(members[0].price), _fmt(members[1].price)
        else:
            # 1 member = single line; 3+ shared quotes are not zones — emit singly
            if len(members) > 2:
                for lv in members:
                    lines.append(_level_line(lv, "S" if lv.kind == "support" else "R",
                                             _fmt(lv.price), ".", keys, prof_prices,
                                             confluence_tol, result))
                continue
            p1, p2 = _fmt(first.price), "."
        lines.append(_level_line(first, prefix, p1, p2, keys, prof_prices,
                                 confluence_tol, result))

    for kind, price in profile_levels:
        if kind in _PROFILE_KINDS:
            lines.append(f"P {kind} {_fmt(price)}")
    return "\n".join(lines)


def _level_line(lv: Level, prefix: str, p1: str, p2: str, keys: set[float],
                prof_prices: list[float], tol: float, result: ParseResult) -> str:
    parts = [prefix, p1, p2, _tier(lv)]
    is_key = lv.price in keys
    if is_key:
        parts.append("key")
    if any(abs(lv.price - pp) <= tol for pp in prof_prices):
        parts.append("conf")
    if is_key:
        note = _note_for(lv.price, result)
        if note:
            parts.append(f'"{note}"')
    return " ".join(parts)
