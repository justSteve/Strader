"""Cut the letter down to the part that plans the next session. [st-9r51]

Stage 2 of the richer-extraction plan. The extractor reads ~42k characters of
which ~7k plan tomorrow; the rest is standing doctrine, the trade recap, and —
the part that matters here — Mancini **quoting his own previous letter**.

## The trap this is built around

The 08-13 plan specified segmentation as trivial: `Bull case tomorrow`,
`Bear case tomorrow` and `In summary for tomorrow` were measured 100% reliable,
exactly once each, across the twelve letters then on hand. Re-measured across
all 353 complete letters in the corpus, that is false in two ways that compound:

1. **The header is usually weekday-named, not "tomorrow".** `Bull case Monday:`,
   `Bear case Thursday:`. A `tomorrow`-only marker set misses those outright.
2. **The letter quotes its own prior edition.** Mancini writes "I expanded on
   this yesterday:" and reprints yesterday's bull case verbatim, inside today's
   recap. So the phrase legitimately appears more than once — 205 of 353 letters
   — and the *first* occurrence is the one that is out of date.

Together: taking the first `Bull case tomorrow` in the letter lands on the
**quoted prior letter in 201 of 353 letters (57%)**. That is not a parsing
inconvenience, it is yesterday's directional plan presented as today's, which is
the one error mode Steve is most exposed to (`knowledge/direction-inversion-
watch.md`).

## The rule that works

Anchor on the ladder, then read forward. The `Supports are:` list is where the
forward plan begins — Mancini never quotes a prior letter's ladder — so a
section header only counts if it appears **at or after** that anchor, and the
header pattern is weekday-aware. Measured on the same 353 letters:

    bull     present 336/353 (95.2%)   exactly once, of those: 100.0%
    bear     present 338/353 (95.8%)   exactly once, of those:  98.2%
    summary  present 332/353 (94.1%)   exactly once, of those: 100.0%

The residual absences are real absences — some letters carry no bear case — and
they are **reported in `missing`, never silent**.

## Why there is no boilerplate corpus

The plan's other half was to strip ~17.3k of recurring paragraphs against a
maintained corpus. Anchoring makes that unnecessary: the forward region is a
median 6,869 chars of a 42,319-char letter, an 84% strip against the plan's 57%
target, and it needs no corpus that can drift out of date as Mancini's standing
sections evolve. A maintained list of his boilerplate would be a second thing to
keep true; the anchor is derived from the letter every time.

**This changes nothing about validation.** `validate.check()` still tests every
price against the FULL raw letter, and `listlevels` still scrapes the full text.
This module produces a reading aid for the extraction step, not a new source of
truth — a level Mancini names outside the forward region is still findable, and
still valid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Mancini heads the forward sections with a day name far more often than with
# "tomorrow", and the weekend resend of a Friday letter says "Monday".
_DAY = (r"(?:tomorrow|today|Monday|Tuesday|Wednesday|Thursday|Friday"
        r"|Saturday|Sunday)")

SUPPORTS_RE = re.compile(r"Supports are\s*:", re.I)
RESISTANCES_RE = re.compile(r"Resistances are\s*:", re.I)
# "In terms of lvls I'd bid direct" — the per-level entry guidance, and on some
# days it precedes the ladder, so it can open the forward region.
BID_DIRECT_RE = re.compile(r"In terms of lvls I.{0,3}d bid direct", re.I)
BULL_RE = re.compile(rf"Bull case (?:for )?{_DAY}\s*:", re.I)
BEAR_RE = re.compile(rf"Bear case (?:for )?{_DAY}\s*:", re.I)
SUMMARY_RE = re.compile(rf"In summary(?: for {_DAY})?\s*:", re.I)

# Order is the letter's usual running order and the order sections render in.
SECTION_RES: list[tuple[str, re.Pattern[str]]] = [
    ("supports", SUPPORTS_RE),
    ("bid_direct", BID_DIRECT_RE),
    ("resistances", RESISTANCES_RE),
    ("bull_case", BULL_RE),
    ("bear_case", BEAR_RE),
    ("summary", SUMMARY_RE),
]

# Sections whose absence is worth saying out loud. `supports`/`resistances`
# absent means the letter did not arrive whole; the rest are genuinely optional.
SECTION_NAMES = tuple(name for name, _ in SECTION_RES)

# Substack's own chrome, which survives clean_newsletter and lands at the tail
# of whichever section runs last — usually the summary. It is not Mancini's
# text, and its copyright year is four digits, so a naive price scan over the
# summary reads "© 2026" as a level he named. Line-anchored so the word "Like"
# inside a sentence is untouched, and only honoured near the end (see _TAIL_FRAC).
_FOOTER_RE = re.compile(
    r"\n\s*(?:Like|Restack|Share|Unsubscribe|View in browser|©\s*\d{4})\s*(?:\n|$)",
    re.I)
# A footer marker earlier than this fraction of the text is a coincidence, not
# the footer; leave it alone rather than truncate the plan.
_TAIL_FRAC = 0.80


def strip_footer(text: str) -> str:
    """Drop the Substack footer from the end of ``text``.

    Conservative by construction: only a line-anchored marker, only in the last
    fifth, and only ever removes a suffix. Returns ``text`` unchanged when no
    marker qualifies.
    """
    cut = None
    for m in _FOOTER_RE.finditer(text):
        if m.start() >= len(text) * _TAIL_FRAC:
            cut = m.start()
            break
    return text[:cut].rstrip() if cut is not None else text


@dataclass
class Segments:
    """The forward plan, cut into labelled sections.

    ``sections`` maps a name from ``SECTION_NAMES`` to its text. ``missing``
    names the sections not found — a reported absence, which is the whole point
    of carrying it rather than letting an empty string pass for "he said
    nothing". ``anchored`` is False when no ladder was found and the whole
    letter had to be handed on unsegmented; a caller must treat that as
    degraded, not as a clean parse of a short letter.
    """

    forward_text: str
    sections: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = ()
    anchored: bool = True
    source_len: int = 0
    forward_start: int = 0

    @property
    def kept_fraction(self) -> float:
        return (len(self.forward_text) / self.source_len) if self.source_len else 1.0

    def get(self, name: str) -> str:
        return self.sections.get(name, "")


def forward_start(text: str) -> int | None:
    """Where the next-session plan begins, or None if the ladder is absent.

    The `Supports are:` ladder, and nothing else. Everything before it is recap,
    doctrine, and the quoted prior letter — see the module docstring for why
    that distinction is load-bearing.

    An earlier draft also allowed the bid-direct paragraph to open the region,
    on the reasoning that it sometimes leads. Measured across 355 letters with a
    ladder, it leads in exactly ONE — 2026-03-19, where the hit is Mancini
    quoting his own prior letter 19,242 chars before the real ladder, and the
    concession pulled the forward region back over 19k of recap. The ladder is
    the only anchor Mancini never quotes, which is the entire reason to use it;
    admitting a second marker gives that property away for a case that does not
    occur.
    """
    sup = SUPPORTS_RE.search(text)
    return sup.start() if sup else None


def segment(text: str) -> Segments:
    """Split ``text`` into the forward plan's labelled sections.

    Never raises on a malformed letter: with no ladder to anchor on, the whole
    text comes back with ``anchored=False`` and every section reported missing,
    so the caller is no worse off than reading the letter raw.
    """
    start = forward_start(text)
    if start is None:
        return Segments(forward_text=text, sections={},
                        missing=SECTION_NAMES, anchored=False,
                        source_len=len(text), forward_start=0)

    forward = strip_footer(text[start:])
    # Positions are found in the FORWARD region only. A header in the recap is
    # the quoted prior letter and must never be mistaken for this one.
    found: list[tuple[int, str]] = []
    for name, rx in SECTION_RES:
        m = rx.search(forward)
        if m:
            found.append((m.start(), name))
    found.sort()

    sections: dict[str, str] = {}
    for i, (pos, name) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(forward)
        body = forward[pos:end].strip()
        if body:
            sections[name] = body

    missing = tuple(n for n in SECTION_NAMES if n not in sections)
    return Segments(forward_text=forward, sections=sections, missing=missing,
                    anchored=True, source_len=len(text), forward_start=start)


def render(seg: Segments) -> str:
    """The labelled document handed to the extraction step.

    Missing sections render as an explicit line rather than vanishing, so the
    extractor can tell "Mancini gave no bear case today" from "the segmenter
    dropped it".
    """
    out: list[str] = []
    if not seg.anchored:
        out += [
            "!! NOT ANCHORED — no `Supports are:` ladder found in this letter.",
            "!! The full text follows unsegmented. Treat section boundaries as",
            "!! unverified, and be aware the letter quotes its own prior edition.",
            "",
            seg.forward_text,
        ]
        return "\n".join(out)

    out += [
        "=== MANCINI FORWARD PLAN (segmented) ===",
        f"kept {len(seg.forward_text)} of {seg.source_len} chars "
        f"({seg.kept_fraction*100:.0f}%) — everything before the ladder is recap,",
        "standing doctrine, and Mancini quoting his PREVIOUS letter. None of it",
        "plans this session.",
        "",
    ]
    for name in SECTION_NAMES:
        body = seg.get(name)
        heading = f"--- {name.upper().replace('_', ' ')} ---"
        if body:
            out += [heading, body, ""]
        else:
            out += [heading, "(absent in this letter)", ""]
    if seg.missing:
        out.append(f"SECTIONS ABSENT: {', '.join(seg.missing)}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """`python -m runbook.mancini.segment` — segment a cleaned letter."""
    import argparse
    import sys
    from pathlib import Path

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", nargs="?", help="cleaned letter (default: stdin)")
    ap.add_argument("--out", help="write the segmented plan here")
    ap.add_argument("--stats", action="store_true",
                    help="print the size reduction and absent sections only")
    args = ap.parse_args(argv)

    text = (Path(args.file).read_text(encoding="utf-8") if args.file
            else sys.stdin.read())
    seg = segment(text)
    if args.stats:
        print(f"anchored={seg.anchored} kept={len(seg.forward_text)}/{seg.source_len} "
              f"({seg.kept_fraction*100:.0f}%) "
              f"sections={sorted(seg.sections)} missing={list(seg.missing)}")
        return 0
    rendered = render(seg)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
        print(f"segmented plan: {args.out} "
              f"({len(seg.forward_text)} of {seg.source_len} chars, "
              f"{seg.kept_fraction*100:.0f}%)")
        if seg.missing:
            print(f"sections absent: {', '.join(seg.missing)}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
