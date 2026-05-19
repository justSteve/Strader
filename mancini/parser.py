"""
Parse Mancini EOD email into structured review steps and levels.
"""
import re
from dataclasses import dataclass, field


@dataclass
class Slide:
    """One sentence from the recap, mapped to a chart moment."""
    section: str        # parent sub-header (e.g. "Friday Morning")
    sentence: str       # the sentence text
    time_anchor: str    # e.g. "9:55AM" — EST, or "" if none in sentence
    price_levels: list[float] = field(default_factory=list)
    direction: str = ""
    capture_file: str = ""  # resolved later from capture pool


@dataclass
class ReviewStep:
    title: str
    time_anchor: str  # e.g. "9:55AM" — EST
    price_levels: list[float] = field(default_factory=list)
    direction: str = ""  # "sell_to" | "rip_to" | "hold"
    text_excerpt: str = ""


@dataclass
class Level:
    price: float
    annotation: str = ""  # "major", "minor", or custom note


@dataclass
class ManciniEmail:
    date: str
    subject: str
    slides: list[Slide] = field(default_factory=list)
    review_steps: list[ReviewStep] = field(default_factory=list)
    support_levels: list[Level] = field(default_factory=list)
    resistance_levels: list[Level] = field(default_factory=list)
    key_levels: list[float] = field(default_factory=list)
    basic_themes: str = ""
    other: str = ""


def extract_section(text: str, start_marker: str, end_markers: list[str]) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = len(text)
    for marker in end_markers:
        pos = text.find(marker, start)
        if pos != -1 and pos < end:
            end = pos
    return text[start:end].strip()


def parse_levels(level_text: str) -> list[Level]:
    """Parse 'Supports are: 7442, 7435 (major), ...' into Level objects."""
    levels = []
    pattern = re.compile(r'(\d{4}(?:\.\d+)?)\s*(?:\(([^)]+)\))?')
    for match in pattern.finditer(level_text):
        price = float(match.group(1))
        annotation = match.group(2) or ""
        levels.append(Level(price=price, annotation=annotation))
    return levels


def parse_review_steps(recap_text: str) -> list[ReviewStep]:
    """Split Trade Recap into steps based on sub-headers.

    Sub-headers are lines with heavy whitespace prefix or distinctive
    patterns like 'Thursday Evening', 'Friday Morning', 'The 9:55AM ...'
    """
    header_pattern = re.compile(
        r'^\s{10,}(.+?)$|^((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(?:Evening|Morning|Afternoon).*)$|^(The\s+\d{1,2}:\d{2}[AP]M\s+.+)$',
        re.MULTILINE
    )

    headers = list(header_pattern.finditer(recap_text))
    if not headers:
        return [ReviewStep(
            title="Full Recap",
            time_anchor="",
            text_excerpt=recap_text[:500]
        )]

    steps = []
    for i, match in enumerate(headers):
        title = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        if not title or title.startswith("NOTE:"):
            continue

        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(recap_text)
        body = recap_text[start:end].strip()

        time_anchor = extract_time_anchor(body)
        price_levels = extract_prices(body)
        direction = infer_direction(body)

        steps.append(ReviewStep(
            title=title,
            time_anchor=time_anchor,
            price_levels=price_levels,
            direction=direction,
            text_excerpt=body[:600]
        ))

    return steps


def extract_time_anchor(text: str) -> str:
    """Find the most prominent time reference in a step's text."""
    matches = re.findall(r'\d{1,2}:\d{2}\s*[AP]M', text, re.IGNORECASE)
    return matches[0] if matches else ""


def extract_prices(text: str) -> list[float]:
    """Extract ES price levels (4-digit numbers in 5000-9999 range)."""
    matches = re.findall(r'\b(7\d{3})\b', text)
    return sorted(set(float(m) for m in matches))


def infer_direction(text: str) -> str:
    """Heuristic: is this step about a sell, a rip, or a hold?"""
    lower = text.lower()
    sell_signals = ["elevator down", "sold", "sell", "flush", "knife"]
    rip_signals = ["ripped", "rip", "squeeze", "rallied", "rally"]
    sell_count = sum(lower.count(s) for s in sell_signals)
    rip_count = sum(lower.count(s) for s in rip_signals)
    if sell_count > rip_count:
        return "sell"
    elif rip_count > sell_count:
        return "rip"
    return "hold"


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping quoted material together."""
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', text)
    sentences = []
    for s in raw:
        s = s.strip()
        if len(s) > 15:
            sentences.append(s)
    return sentences


def parse_slides(recap_text: str) -> list[Slide]:
    """Break Trade Recap into per-sentence slides with time anchors.

    Each sentence becomes one slide. Time anchors carry forward from
    the most recent sentence that contained one, so slides without
    an explicit time inherit context from their predecessor.
    """
    header_pattern = re.compile(
        r'^\s{10,}(.+?)$|^((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(?:Evening|Morning|Afternoon).*)$|^(The\s+\d{1,2}:\d{2}[AP]M\s+.+)$',
        re.MULTILINE
    )

    headers = list(header_pattern.finditer(recap_text))
    if not headers:
        return []

    slides = []
    last_time = ""

    for i, match in enumerate(headers):
        section = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        if not section or section.startswith("NOTE:"):
            continue

        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(recap_text)
        body = recap_text[start:end].strip()

        if body.startswith("I do this trade recap section"):
            continue

        last_time = extract_time_anchor(section) or ""

        for sentence in split_sentences(body):
            time_ref = extract_time_anchor(sentence)
            if time_ref:
                last_time = time_ref

            slides.append(Slide(
                section=section,
                sentence=sentence,
                time_anchor=last_time,
                price_levels=extract_prices(sentence),
                direction=infer_direction(sentence),
            ))

    return slides


def match_captures(slides: list[Slide], capture_dir: str,
                   date: str = "") -> list[Slide]:
    """Match each slide to the nearest 5-min screen capture by time.

    Recognizes:
      ES_YYYYMMDD_HHMM.png  (capture tool output)
      ES_HHMM.png           (legacy short form)
      YYYYMMDD_HHMM.png     (date-prefixed)
    """
    from pathlib import Path

    cap_path = Path(capture_dir)
    if not cap_path.exists():
        return slides

    captures = {}
    for f in sorted(cap_path.iterdir()):
        if f.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            continue
        m = re.search(r'(\d{8})_(\d{2})(\d{2})', f.stem)
        if not m:
            m = re.search(r'(?:^|_)(\d{2})(\d{2})$', f.stem)
            if m:
                hh, mm = int(m.group(1)), int(m.group(2))
            else:
                continue
        else:
            hh, mm = int(m.group(2)), int(m.group(3))
        minutes_from_midnight = hh * 60 + mm
        captures[minutes_from_midnight] = str(f)

    if not captures:
        return slides

    cap_times = sorted(captures.keys())

    for slide in slides:
        if not slide.time_anchor:
            continue
        t = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', slide.time_anchor, re.IGNORECASE)
        if not t:
            continue
        h, m, ampm = int(t.group(1)), int(t.group(2)), t.group(3).upper()
        if ampm == 'PM' and h != 12:
            h += 12
        if ampm == 'AM' and h == 12:
            h = 0
        target = h * 60 + m

        closest = min(cap_times, key=lambda ct: abs(ct - target))
        slide.capture_file = captures[closest]

    return slides


def parse_email(plaintext: str, date: str = "", subject: str = "") -> ManciniEmail:
    """Main entry point: parse full email into structured ManciniEmail."""
    boilerplate_end = "On to today: Basic Themes"
    recap_start = "Trade Recap/Daily Summary"
    plan_pattern = re.compile(r'Trade Plan\s+\w+')

    plan_match = plan_pattern.search(plaintext)
    plan_start_marker = plan_match.group(0) if plan_match else "Trade Plan"

    basic_themes = extract_section(
        plaintext, boilerplate_end,
        [recap_start]
    )

    recap_text = extract_section(
        plaintext, recap_start,
        [plan_start_marker, "Trade Plan"]
    )

    plan_text = extract_section(
        plaintext, plan_start_marker,
        ["Unsubscribe", "As always no crystal balls"]
    )

    support_text = ""
    resistance_text = ""
    sup_match = re.search(r'Supports are:(.+?)(?=Resistances are:|In terms of)', plan_text, re.DOTALL)
    res_match = re.search(r'Resistances are:(.+?)(?=As readers know|Bull case|Bear case)', plan_text, re.DOTALL)
    if sup_match:
        support_text = sup_match.group(1)
    if res_match:
        resistance_text = res_match.group(1)

    return ManciniEmail(
        date=date,
        subject=subject,
        slides=parse_slides(recap_text),
        review_steps=parse_review_steps(recap_text),
        support_levels=parse_levels(support_text),
        resistance_levels=parse_levels(resistance_text),
        key_levels=extract_key_levels(plan_text),
        basic_themes=basic_themes,
        other=""
    )


def extract_key_levels(plan_text: str) -> list[float]:
    """Pull 4-digit prices Mancini names in bull/bear case + summary sections.

    These are levels he explicitly cites, not just listed. Returned as a
    deduplicated sorted list. Cross-referencing with the published S/R
    arrays happens in the emitter.
    """
    case_text_parts = []
    for header in ("Bull case", "Bear case", "In summary"):
        pattern = re.compile(
            rf'{re.escape(header)}[^\n]*?:.+?(?=(?:Bull case|Bear case|In summary|Unsubscribe)|\Z)',
            re.DOTALL,
        )
        for m in pattern.finditer(plan_text):
            case_text_parts.append(m.group(0))

    if not case_text_parts:
        return []

    combined = " ".join(case_text_parts)
    prices = re.findall(r'\b(7\d{3})\b', combined)
    return sorted({float(p) for p in prices})
