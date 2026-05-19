"""Render a Mancini session replay from parsed slides.

Filters to action-relevant slides (price levels or directional signal),
groups by section, and outputs a time-ordered narrative. Designed for
terminal/tmux display or markdown archiving.
"""
from __future__ import annotations

from pathlib import Path

from .parser import ManciniEmail, Slide


_TEACHING_PHRASES = [
    "it took me years",
    "it doesnt matter if",
    "it doesn't matter if",
    "profitable trading looks like",
    "i do the same template",
    "i do this trade recap",
    "for one reason mostly",
    "new traders",
    "brand-new traders",
    "newer/learning readers",
    "whole industry",
    "flipping back and forth",
]


def _is_action_slide(slide: Slide) -> bool:
    lower = slide.sentence.lower()
    if any(p in lower for p in _TEACHING_PHRASES):
        return False
    return bool(slide.price_levels) or slide.direction in ("sell", "rip")


def _format_prices(prices: list[float]) -> str:
    if not prices:
        return ""
    return " ".join(str(int(p)) for p in prices)


def _direction_badge(d: str) -> str:
    if d == "sell":
        return "SELL"
    if d == "rip":
        return " RIP"
    return "    "


def render_replay(email: ManciniEmail, *, action_only: bool = True) -> str:
    """Render session replay as formatted text.

    action_only=True filters to slides with price levels or sell/rip direction.
    """
    lines: list[str] = []
    lines.append(f"# Session Replay — {email.date or 'unknown'}")
    lines.append(f"# {email.subject}")
    lines.append("")

    sections: dict[str, list[Slide]] = {}
    for s in email.slides:
        sections.setdefault(s.section, []).append(s)

    for sec_name, slides in sections.items():
        if action_only:
            slides = [s for s in slides if _is_action_slide(s)]
        if not slides:
            continue

        lines.append(f"## {sec_name}")
        lines.append("")

        for slide in slides:
            anchor = slide.time_anchor or "      "
            badge = _direction_badge(slide.direction)
            prices = _format_prices(slide.price_levels)

            price_col = f"[{prices}]" if prices else ""
            header = f"  {anchor:>8}  {badge}  {price_col}"
            lines.append(header)

            text = slide.sentence.strip()
            wrapped = _wrap(text, indent=16, width=100)
            lines.append(wrapped)
            lines.append("")

        lines.append("")

    sup_prices = sorted([l.price for l in email.support_levels], reverse=True)
    res_prices = sorted([l.price for l in email.resistance_levels])
    key = set(email.key_levels)

    lines.append("## Level Reference")
    lines.append("")
    lines.append("  Supports:    " + "  ".join(
        f"**{int(p)}**" if p in key else str(int(p)) for p in sup_prices[:15]
    ))
    lines.append("  Resistances: " + "  ".join(
        f"**{int(p)}**" if p in key else str(int(p)) for p in res_prices[:15]
    ))
    lines.append(f"  Key levels:  {', '.join(str(int(p)) for p in sorted(key))}")
    lines.append("")

    return "\n".join(lines)


def _wrap(text: str, indent: int, width: int) -> str:
    prefix = " " * indent
    words = text.split()
    lines: list[str] = []
    current = prefix

    for word in words:
        if len(current) + 1 + len(word) > width and current.strip():
            lines.append(current)
            current = prefix + word
        else:
            current = current + " " + word if current.strip() else prefix + word

    if current.strip():
        lines.append(current)
    return "\n".join(lines)
