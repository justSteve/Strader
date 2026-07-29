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

import re
import subprocess
from typing import Sequence

from .chart import key_prices
from .schema import Level, ParseResult

CONFLUENCE_TOLERANCE_PTS = 2.0
_PROFILE_KINDS = ("poc", "vah", "val", "lvn", "hvn")


def _fmt(price: float) -> str:
    return f"{price:g}"


def _tier(level: Level) -> str:
    return "major" if "major" in (level.label or "").lower() else "minor"


# Commentary categories that belong in the letter summary and never on a chart
# label. Steve 2026-07-29: "I never care what M. is holding. today's 7533 gives
# me Bull Case: that info is for the letter summary, not labels."
_LETTER_SUMMARY_TAGS = frozenset({
    "positioning", "runner", "bull-case", "bear-case", "summary", "lean",
    "catalyst", "fomc", "mode2", "targets", "breakout", "breakdown",
    "advanced", "shorts",
})

# Ordered most-useful-first. A label earns text only when the letter says
# something narrow about THAT level's quality \u2014 how well it has held, how it was
# built, where it sits in the range. Everything is drawn from a fixed vocabulary
# so labels stay short and comparable across days; the old behaviour spliced 57
# characters of narrative and left mid-word stubs like "runner f...".
_DESCRIPTORS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), descriptor) for pattern, descriptor in (
        (r"\brange (?:support|resistance)\b",                 "range edge"),
        (r"\b(?:so )?well tested\b",                          "well tested"),
        (r"\bvery strong\b",                                  "very strong"),
        (r"\b(?:major )?support cluster\b",                   "major cluster"),
        (r"\bbig (?:support|resistance)\b",                   "big level"),
        (r"\bstrong (?:support|resistance)\b",                "strong"),
        (r"\bobvious shelf\b|\bbuilt the shelf\b|\bshelf\b",  "shelf"),
        (r"\bfirst support down\b",                           "first support"),
        (r"\bfirst resistance\b",                             "first resistance"),
    )
)


_PRICE_MENTION = re.compile(r"\b(\d{4}(?:\.\d+)?)\b")


def _owns(text: str, at: int, price: float) -> bool:
    """True if the phrase at offset ``at`` describes ``price``.

    A descriptor belongs to the nearest price mentioned BEFORE it. One
    commentary routinely names several levels \u2014 "Safer: wait for 7398 to hold,
    then recover the 7418 shelf" anchors on 7398, but the shelf is 7418's.
    Reading the whole sentence would hang that shelf on the wrong level.
    A phrase with no price before it (e.g. a sentence opening "Range support
    is now 7418") describes the level the commentary is anchored on.
    """
    owner = None
    for m in _PRICE_MENTION.finditer(text):
        if m.start() >= at:
            break
        owner = float(m.group(1))
    return owner is None or abs(owner - price) < 1e-9


def _note_for(price: float, result: ParseResult) -> str | None:
    """A short descriptor of this level's own quality, or None.

    Deliberately NOT a summary of the day's plan. Commentary tagged as
    positioning, bull/bear case, regime or catalyst is rejected outright \u2014 it is
    about the session, not about the level, and Steve reads that in the letter
    summary rather than off the chart. What survives is scanned for a
    level-quality phrase from ``_DESCRIPTORS``, attributed by ``_owns``, so a
    label reads "well tested" instead of a truncated sentence. No match means no
    note, which is the common and correct outcome: most levels have nothing
    particular said about them.
    """
    for c in result.commentary:
        if _LETTER_SUMMARY_TAGS.intersection(t.lower() for t in c.tags):
            continue
        anchors = getattr(c.trigger, "anchor_prices", None) or []
        if not any(abs(a - price) < 1e-9 for a in anchors):
            continue
        text = c.text.lower()
        for pattern, descriptor in _DESCRIPTORS:
            if any(_owns(text, m.start(), price) for m in pattern.finditer(text)):
                return descriptor
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


def _default_run(cmd: list[str], text: str) -> int:
    proc = subprocess.run(cmd, input=text.encode("utf-16-le"), timeout=15)
    return proc.returncode


def push_clipboard(payload: str, *, run=_default_run) -> int:
    """Push the payload to the Windows clipboard via clip.exe (WSL interop).

    clip.exe expects UTF-16LE from a pipe; plain UTF-8 arrives mojibake'd
    (same class of bug as the WSL backup scripts, spec Known hazards)."""
    return run(["clip.exe"], payload)


def ceiling_probe(kb: int) -> str:
    """Synthetic payload of ~kb KB for the input.text_area ceiling test.

    Valid v1 format with an obviously-fake date so a leftover probe paste
    trips the STALE banner instead of masquerading as a real day."""
    lines = [f"v1 2099-01-01 ES"]
    price = 1000.0
    while len("\n".join(lines).encode()) < kb * 1024 - 24:
        lines.append(f"S {price:g} . minor")
        price += 0.25
    return "\n".join(lines)
