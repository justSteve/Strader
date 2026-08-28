"""Overnight interaction brief. [st-doz]

Mancini writes his letter at or near end-of-day on the day BEFORE the session
the plan targets. By the time Steve reads the parsed plan, overnight price
action has always already interacted with the levels the letter references —
some tested, some broken, some reclaimed. This module spells that out: it
pulls the /ES candles from the letter's write-time to now and reports, per
level, what has already happened to it.

The state definitions are the SAME close-based ones the Pine renderer uses
(pine/mancini_forecast.pine), so the written brief and the chart never
disagree:

  touched   — a candle traded within ``tolerance`` of the level
  held      — touched, and the candle CLOSED on the correct side
  broken    — a candle closed beyond the level by MORE than tolerance
              (close, not wick — wicks are flush noise)
  reclaimed — after a break, a close back on the original side
              (the Failed Breakdown pattern, in place)

Degradation contract: ``build_overnight_section`` never raises. If the Schwab
token is dead, the gate key is absent, or the response is empty, it returns a
one-line section saying the overnight data was unreachable — the parse and
publish must never block on this supplement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from . import schema
from .schema import Level, ParseResult

logger = logging.getLogger("runbook.mancini")

CENTRAL = ZoneInfo("America/Chicago")
EASTERN = ZoneInfo("America/New_York")

# Mancini's letters go out at or near 4pm ET the day before the plan-day; the
# overnight window opens there. Verbatim source: letter headers ("originally
# sent Friday at 4pm") and blob timestamps (~19:00 UTC).
LETTER_HOUR_ET = 16

DEFAULT_TOLERANCE_PTS = 2.0


@dataclass
class LevelInteraction:
    price: float
    kind: str                      # support | resistance
    major: bool
    # Mancini's own words about the level, carried through from Level. [st-ui8m]
    # `major` above is a boolean derived from the same field and is NOT a
    # substitute: it answers "is this a major?" and throws away "nice shelf of
    # lows from noon Thursday to midnight Friday", which is the part Steve reads
    # the plan for. Without these two the callout dies here, before tracker.py
    # ever sees it, and no amount of fixing build_state alone recovers it.
    label: str = ""
    source_quote: str = ""
    # Which words of the callout are quotation vs extractor gloss [st-9r51].
    # Same drop-site reasoning as label/source_quote above: the sentinel decides
    # whether it may attribute the callout to Mancini, so the attribution has to
    # survive construction here or the decision cannot be made downstream.
    callout_quotes: list[str] = field(default_factory=list)
    callout_attribution: str = ""
    # Typed level fields [st-9r51]. Same drop-site reasoning as above: the
    # sentinel branches on these, so they must survive construction here.
    intent: str = "unstated"
    conviction: str = "unstated"
    setup: str = "none"
    state: str = "untouched"       # untouched | tested-held | broken | reclaimed
    touches: int = 0
    defenses: int = 0              # touched-and-held closes
    break_time: str | None = None  # "HH:MM CT"
    reclaim_time: str | None = None
    extreme: float | None = None   # worst excursion beyond the level while broken
    # Evidence trail [st-qih1]: every state-changing event with the candle row
    # behind it, so any claim ("7549 held three times") is checkable against
    # the tape rather than believed. The brief ignores these; the level-state
    # tracker serializes them.
    first_touch: str | None = None   # ISO UTC of the first touching candle
    last_event_ts: str | None = None
    events: list = field(default_factory=list)


@dataclass
class OvernightReport:
    interactions: list[LevelInteraction] = field(default_factory=list)
    last_close: float | None = None
    window_start: str = ""         # "Mon 15:00 CT" style
    window_end: str = ""
    candle_count: int = 0
    error: str | None = None


def letter_window_start(plan_date: str) -> datetime:
    """UTC datetime of the letter's write-time: 4pm ET the day before plan-day."""
    day = datetime.strptime(plan_date, "%Y-%m-%d").date()
    prior = day - timedelta(days=1)
    local = datetime(prior.year, prior.month, prior.day, LETTER_HOUR_ET, 0,
                     tzinfo=EASTERN)
    return local.astimezone(timezone.utc)


def _fmt_ct(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(
        CENTRAL).strftime("%a %H:%M CT")


def _iso_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(
        timespec="seconds")


def _evidence(it: "LevelInteraction", event: str, c: dict) -> None:
    ts = _iso_utc(c["datetime"])
    it.last_event_ts = ts
    it.events.append({"event": event, "ts": ts,
                      "candle": {k: c[k] for k in
                                 ("open", "high", "low", "close") if k in c}})


def fetch_overnight_candles(start_utc: datetime,
                            end_utc: datetime | None = None) -> list[dict]:
    """Five-minute /ES candles from Schwab, extended hours included.

    Raises on anything unusable; build_overnight_section catches and degrades.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from broker_schwab.client import create_client

    client = create_client()
    end_utc = end_utc or datetime.now(tz=timezone.utc)
    r = client.get_price_history_every_five_minutes(
        "/ES", start_datetime=start_utc, end_datetime=end_utc,
        need_extended_hours_data=True,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Schwab price history HTTP {r.status_code}")
    data = r.json()
    candles = data.get("candles", [])
    if data.get("empty") or not candles:
        raise RuntimeError("Schwab returned no candles for /ES")
    return candles


def compute_interactions(levels: Sequence[Level], candles: Sequence[dict],
                         tolerance: float = DEFAULT_TOLERANCE_PTS,
                         ) -> list[LevelInteraction]:
    """Run every ladder level through the candle series, close-based."""
    out: list[LevelInteraction] = []
    for lv in levels:
        if lv.kind not in ("support", "resistance"):
            continue
        it = LevelInteraction(
            price=lv.price, kind=lv.kind,
            major=schema.is_major(lv.label),
            label=lv.label, source_quote=lv.source_quote,
            callout_quotes=list(getattr(lv, "callout_quotes", []) or []),
            callout_attribution=getattr(lv, "callout_attribution", "") or "",
            intent=getattr(lv, "intent", "") or "unstated",
            conviction=getattr(lv, "conviction", "") or "unstated",
            setup=getattr(lv, "setup", "") or "none",
        )
        is_sup = lv.kind == "support"
        for c in candles:
            close = c["close"]
            touched = (c["low"] <= it.price + tolerance
                       and c["high"] >= it.price - tolerance)
            held_close = close > it.price if is_sup else close < it.price
            broken_close = (close < it.price - tolerance if is_sup
                            else close > it.price + tolerance)

            if touched:
                it.touches += 1
                if it.first_touch is None:
                    it.first_touch = _iso_utc(c["datetime"])
                    _evidence(it, "first_touch", c)
            if it.state in ("untouched",) and touched:
                it.state = "tested-held"
            if it.state in ("untouched", "tested-held") and broken_close:
                it.state = "broken"
                it.break_time = _fmt_ct(c["datetime"])
                it.extreme = c["low"] if is_sup else c["high"]
                _evidence(it, "break", c)
            elif it.state == "broken":
                worst = c["low"] if is_sup else c["high"]
                if it.extreme is None or (worst < it.extreme if is_sup
                                          else worst > it.extreme):
                    it.extreme = worst
                if held_close:
                    it.state = "reclaimed"
                    it.reclaim_time = _fmt_ct(c["datetime"])
                    _evidence(it, "reclaim", c)
            if it.state in ("tested-held", "reclaimed") and touched and held_close:
                it.defenses += 1
                _evidence(it, "defended_close", c)
        out.append(it)
    return out


_SIGNIFICANCE = {"reclaimed": 0, "broken": 1, "tested-held": 2, "untouched": 3}


DEFAULT_SECTION_TITLE = "Overnight interaction — what has already happened to these levels"


def render_section(report: OvernightReport, title: str | None = None) -> str:
    """The '## Overnight interaction' markdown block for the desk plan doc.

    ``title`` overrides the heading text (no leading ``## ``) — the 08:15 /
    manual refresh [st-vxbw] re-renders this block intraday, when "overnight"
    is no longer the honest word for the window."""
    lines = [f"## {title or DEFAULT_SECTION_TITLE}", ""]
    if report.error:
        lines.append(f"_Overnight data unavailable ({report.error}) — "
                     "section skipped. The chart's state markers still track "
                     "from the session open._")
        return "\n".join(lines)

    lines.append(f"> /ES five-minute candles, {report.window_start} → "
                 f"{report.window_end} ({report.candle_count} candles). "
                 f"Last price {report.last_close:g}. Same close-based "
                 "definitions as the chart renderer.")
    lines.append("")

    active = [i for i in report.interactions if i.state != "untouched"]
    active.sort(key=lambda i: (_SIGNIFICANCE[i.state], -i.touches))
    for it in active:
        tier = "major " if it.major else ""
        side = "support" if it.kind == "support" else "resistance"
        dist = (report.last_close - it.price) if report.last_close else 0.0
        where = (f"price now {abs(dist):.1f} above" if dist > 0
                 else f"price now {abs(dist):.1f} below")
        if it.state == "reclaimed":
            extreme = f" (ran to {it.extreme:g})" if it.extreme is not None else ""
            pattern = ("The Failed Breakdown pattern has already printed here "
                       "overnight." if it.kind == "support" else
                       "Price poked above and was rejected back under - a "
                       "failed breakout overnight.")
            lines.append(
                f"- **{it.price:g} {tier}{side}: RECLAIMED** — broke at "
                f"{it.break_time}{extreme}, closed back on the right side at "
                f"{it.reclaim_time}. {pattern} {where}.")
        elif it.state == "broken":
            extreme = f", ran to {it.extreme:g}" if it.extreme is not None else ""
            lines.append(
                f"- **{it.price:g} {tier}{side}: BROKEN** — closed through at "
                f"{it.break_time}{extreme} and has not been recovered. Treat "
                f"the level as flipped until it reclaims. {where}.")
        else:
            lines.append(
                f"- {it.price:g} {tier}{side}: tested and held — "
                f"{it.touches} touch{'es' if it.touches != 1 else ''}, "
                f"{it.defenses} defended close{'s' if it.defenses != 1 else ''}. "
                f"{where}.")
    untouched = [i for i in report.interactions if i.state == "untouched"]
    if untouched:
        lines.append(f"- {len(untouched)} of {len(report.interactions)} levels "
                     "untouched overnight.")
    return "\n".join(lines)


def build_overnight_report(result: ParseResult,
                           fetch: Callable[..., list[dict]] | None = None,
                           tolerance: float = DEFAULT_TOLERANCE_PTS) -> OvernightReport:
    """Fetch → compute, as data. Never raises — errors land in ``report.error``.

    Split out of ``build_overnight_section`` for the refresh path [st-vxbw],
    which wants the counts (broken / reclaimed / held) for its terminal summary
    as well as the rendered block."""
    report = OvernightReport()
    try:
        start = letter_window_start(result.date)
        candles = (fetch or fetch_overnight_candles)(start)
        report.interactions = compute_interactions(result.levels, candles,
                                                   tolerance)
        report.last_close = candles[-1]["close"]
        report.window_start = _fmt_ct(candles[0]["datetime"])
        report.window_end = _fmt_ct(candles[-1]["datetime"])
        report.candle_count = len(candles)
    except Exception as e:  # noqa: BLE001 — degradation contract
        logger.warning("overnight brief unavailable: %s", e)
        report.error = str(e)
    return report


def build_overnight_section(result: ParseResult,
                            fetch: Callable[..., list[dict]] | None = None,
                            tolerance: float = DEFAULT_TOLERANCE_PTS,
                            title: str | None = None) -> str:
    """Orchestrate fetch → compute → render. Never raises."""
    return render_section(build_overnight_report(result, fetch, tolerance), title)
