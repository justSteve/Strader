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
    break_time: str | None = None  # "HH:MM CT" — the latest break
    reclaim_time: str | None = None
    rebreaks: int = 0              # times a reclaimed level was lost again
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
    # Which ES contract the candles are — the letter's contract, resolved from
    # the ladder, not Schwab's continuous /ES [st-7xzw]. ``basis`` is the OTHER
    # quarterly's last close minus this one's, when both were fetched: the
    # number a reader on the other contract's chart adds to every level.
    contract: str = ""
    resolution: str = ""
    basis: float | None = None
    basis_contract: str = ""
    candles: list = field(default_factory=list)


# --- the letter's contract -------------------------------------------------
#
# 2026-09-14 (st-7xzw): Schwab's continuous /ES had rolled to ESZ26 over the
# weekend while Mancini's ladder was still on ESU26, ~67 points lower. The
# brief measured December candles against September levels and reported
# 54 of 58 levels untouched when 7620, 7610 and 7605 were already gone and
# 7595 had been tested. The letter itself says which contract it is on: the
# price as he writes sits between his highest support and lowest resistance
# ("First support as of writing is 7650" ... "Resistances are: 7671 ..."), so
# the quarterly whose write-time candle opens inside that gap is his.

QUARTERLY_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}


def third_friday(year: int, month: int) -> "date":
    from datetime import date as _date
    d = _date(year, month, 15)
    # weekday(): Mon=0 ... Fri=4. Third Friday is the first Friday on/after the 15th.
    return d + timedelta(days=(4 - d.weekday()) % 7)


def quarterly_contracts(plan_date: str, n: int = 2) -> list[str]:
    """The ``n`` nearest ES quarterlies still trading on plan-day, front first.

    Expiry is the third Friday of Mar/Jun/Sep/Dec; on expiry day itself the
    contract still trades into the open, so it stays the front that day."""
    day = datetime.strptime(plan_date, "%Y-%m-%d").date()
    out: list[str] = []
    year, month = day.year, day.month
    while len(out) < n:
        if month in QUARTERLY_CODES and third_friday(year, month) >= day:
            out.append(f"/ES{QUARTERLY_CODES[month]}{year % 100:02d}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return out


def ladder_gap(levels: Sequence[Level]) -> tuple[float | None, float | None]:
    """(highest support, lowest resistance) — where price sat as he wrote."""
    sups = [lv.price for lv in levels if lv.kind == "support"]
    ress = [lv.price for lv in levels if lv.kind == "resistance"]
    return (max(sups) if sups else None), (min(ress) if ress else None)


def _gap_distance(price: float, top_sup: float | None, bot_res: float | None) -> float:
    """0.0 inside the gap; otherwise how far outside. One-sided when the ladder
    lacks a side."""
    if top_sup is not None and price < top_sup:
        return top_sup - price
    if bot_res is not None and price > bot_res:
        return price - bot_res
    return 0.0


def _takes_symbol(fetch: Callable) -> bool:
    import inspect
    try:
        params = inspect.signature(fetch).parameters
    except (TypeError, ValueError):
        return False
    return "symbol" in params or any(p.kind == p.VAR_KEYWORD for p in params.values())


@dataclass
class ContractResolution:
    symbol: str
    candles: list
    reason: str
    basis: float | None = None          # other.last_close - chosen.last_close
    basis_contract: str = ""
    write_prices: dict = field(default_factory=dict)   # symbol -> first open
    errors: dict = field(default_factory=dict)         # symbol -> str


def _series_collapsed(fetched: dict[str, list[dict]]) -> bool:
    """True when every fetched series is the same candles — Schwab ignored
    the month suffix."""
    # Compare on settled candles only: the two pulls are seconds apart and the
    # forming candle (and sometimes the count) differs between them.
    n = min(len(c) for c in fetched.values())
    if n < 2:
        return len({(float(c[0]["open"]), c[0]["datetime"]) for c in fetched.values()}) == 1
    k = n - 2
    sigs = {(c[0]["datetime"], float(c[0]["open"]), float(c[0]["close"]),
             c[k]["datetime"], float(c[k]["close"])) for c in fetched.values()}
    return len(sigs) == 1


def fetch_contract_quotes(symbols: Sequence[str]) -> dict[str, dict]:
    """Per contract from Schwab quotes — these DO carry the month:
    ``{"last": lastPrice, "close": closePrice}``. ``close`` is the prior
    daily settle, struck 4pm ET — the letter's write time to the minute, and
    immune to the weekend gap that Sunday's first candle carries."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from broker_schwab.client import create_client

    r = create_client().get_quotes(list(symbols))
    if r.status_code != 200:
        raise RuntimeError(f"Schwab quotes HTTP {r.status_code}")
    out: dict[str, dict] = {}
    for sym, info in r.json().items():
        q = info.get("quote") or {}
        if q.get("lastPrice") is not None:
            out[sym] = {"last": float(q["lastPrice"]),
                        "close": float(q["closePrice"]) if q.get("closePrice") is not None else None}
    return out


def resolve_letter_contract(result: ParseResult, start_utc: datetime,
                            fetch: Callable[..., list[dict]] | None = None,
                            end_utc: datetime | None = None,
                            candidates: Sequence[str] | None = None,
                            quote_fetch: Callable[..., dict[str, float]] | None = None,
                            ) -> ContractResolution:
    """Pick the quarterly Mancini's ladder is written on. Raises only when no
    candidate returns candles at all (callers degrade the same way they do for
    a dead feed).

    ``fetch(start_utc, end_utc, symbol=...)`` per candidate; the write-time
    price is the first candle's open. The contract that opens inside the
    ladder gap wins; if none does, the nearest to it; ties go to the front."""
    fetch = fetch or fetch_overnight_candles
    if not _takes_symbol(fetch):
        # A fetch that cannot name a contract (test fixtures, an older caller)
        # gets the continuous series and says so — never two identical pulls
        # dressed up as a resolution.
        candles = fetch(start_utc) if end_utc is None else fetch(start_utc, end_utc)
        if not candles:
            raise RuntimeError("Schwab returned no candles for /ES")
        return ContractResolution(symbol="/ES", candles=candles,
                                  reason="fetch does not distinguish contracts — continuous /ES")
    candidates = list(candidates or quarterly_contracts(result.date))
    top_sup, bot_res = ladder_gap(result.levels)
    fetched: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}
    for sym in candidates:
        try:
            c = fetch(start_utc, end_utc, symbol=sym)
            if c:
                fetched[sym] = c
            else:
                errors[sym] = "no candles"
        except Exception as e:  # noqa: BLE001 — one dead candidate is not fatal
            errors[sym] = str(e)
    if not fetched:
        raise RuntimeError("no ES contract returned candles: "
                           + "; ".join(f"{s}: {m}" for s, m in errors.items()))

    # Schwab's price history serves ONE series whatever month suffix it is
    # given (measured 2026-09-14 08:08 CT: /ESU26 and /ESZ26 both came back as
    # the December candles, basis +0). Quotes DO distinguish contracts, so
    # when the series collapse, measure the live basis from quotes, work out
    # which contract Schwab actually served, and shift it onto the letter's.
    # One measurement, stamped, not a rolling estimator [Steve 2026-09-12].
    shift_note = ""
    shifts: dict[str, float] = {}
    quotes: dict[str, dict] = {}
    if len(fetched) >= 2:
        try:
            quotes = (quote_fetch or fetch_contract_quotes)(list(fetched))
        except Exception as e:  # noqa: BLE001 — quotes down must not kill the brief
            logger.warning("contract quotes unavailable: %s", e)
            quotes = {}
    if len(fetched) >= 2 and _series_collapsed(fetched):
        if len(quotes) >= 2:
            served_close = float(next(iter(fetched.values()))[-1]["close"])
            served = min(quotes, key=lambda s: abs(quotes[s]["last"] - served_close))
            stamp = datetime.now(tz=timezone.utc).astimezone(CENTRAL).strftime("%H:%M CT")
            base = fetched[served]
            for s in list(fetched):
                shifts[s] = round((quotes[s]["last"] - quotes[served]["last"]) * 4) / 4   # tick-rounded
                if s != served and shifts[s] != 0.0:
                    fetched[s] = [dict(c, open=c["open"] + shifts[s], high=c["high"] + shifts[s],
                                       low=c["low"] + shifts[s], close=c["close"] + shifts[s])
                                  for c in base]
            shift_note = (f"; Schwab served one series for every month ({served} by quote); "
                          f"the other contract is that series shifted by the live basis "
                          f"measured at {stamp}")
        else:
            shift_note = "; Schwab served one series for every month and quotes were unavailable to separate them"

    # Write-time price: the prior settle from the contract's own quote (4pm
    # ET, when he writes) — Sunday's first candle sits past the weekend gap
    # and on 2026-09-14 would have pointed at the wrong contract. Fall back
    # to the first candle's open when the quote carries no close.
    write_prices = {}
    write_src = "first candle open"
    for s, c in fetched.items():
        q = quotes.get(s) or {}
        if q.get("close") is not None:
            write_prices[s] = float(q["close"])
            write_src = "prior settle from quotes"
        else:
            write_prices[s] = float(c[0]["open"])
    if top_sup is None and bot_res is None:
        chosen = candidates[0] if candidates[0] in fetched else next(iter(fetched))
        reason = "no ladder to test against — front contract assumed"
    else:
        ranked = sorted(fetched, key=lambda s: (_gap_distance(write_prices[s], top_sup, bot_res),
                                                candidates.index(s)))
        chosen = ranked[0]
        d = _gap_distance(write_prices[chosen], top_sup, bot_res)
        gap = (f"{top_sup:g} support" if top_sup is not None else "no support") + " / " + \
              (f"{bot_res:g} resistance" if bot_res is not None else "no resistance")
        if d == 0.0:
            reason = (f"write-time price {write_prices[chosen]:g} ({write_src}) sits inside the "
                      f"letter's gap ({gap})")
        else:
            reason = (f"no contract's write-time price ({write_src}) fell inside the letter's "
                      f"gap ({gap}); {chosen} was nearest at {write_prices[chosen]:g}")
        if len(fetched) == 1:
            reason += f"; only contract with data ({', '.join(errors) or 'none other tried'})"
    reason += shift_note
    if shifts.get(chosen):
        reason += f" ({chosen} = served series {shifts[chosen]:+g})"
    res = ContractResolution(symbol=chosen, candles=fetched[chosen], reason=reason,
                             write_prices=write_prices, errors=errors)
    others = [s for s in fetched if s != chosen]
    if others:
        other = others[0]
        res.basis_contract = other
        res.basis = round(float(fetched[other][-1]["close"]) - float(fetched[chosen][-1]["close"]), 2)
    return res


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
                            end_utc: datetime | None = None,
                            symbol: str = "/ES") -> list[dict]:
    """Five-minute ES candles from Schwab, extended hours included.

    ``symbol`` names the contract (``/ESU26``); the bare continuous ``/ES``
    is Schwab's idea of the front month, which in roll week is not Mancini's
    [st-7xzw] — callers go through ``resolve_letter_contract``.

    Raises on anything unusable; build_overnight_section catches and degrades.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from broker_schwab.client import create_client

    client = create_client()
    end_utc = end_utc or datetime.now(tz=timezone.utc)
    r = client.get_price_history_every_five_minutes(
        symbol, start_datetime=start_utc, end_datetime=end_utc,
        need_extended_hours_data=True,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Schwab price history HTTP {r.status_code} for {symbol}")
    data = r.json()
    candles = data.get("candles", [])
    if data.get("empty") or not candles:
        raise RuntimeError(f"Schwab returned no candles for {symbol}")
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
            if it.state in ("untouched", "tested-held", "reclaimed") and broken_close:
                # A reclaimed level that closes through again is broken again
                # [st-7xzw]: on 2026-09-14 7620 trapped Sunday evening, was
                # reclaimed, then lost for good pre-open — a terminal
                # "reclaimed" would have called the floor held with price
                # twelve points under it.
                if it.state == "reclaimed":
                    it.rebreaks += 1
                    it.reclaim_time = None
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


def basis_note(report: "OvernightReport", tolerance: float = DEFAULT_TOLERANCE_PTS) -> str:
    """One sentence on the other quarterly, when it matters. Empty when the
    two contracts are within tolerance (they never are — the carry is tens of
    points — but a same-contract double fetch must not print nonsense) or
    when only one contract answered."""
    if report.basis is None or not report.basis_contract or abs(report.basis) < tolerance:
        return ""
    other = report.basis_contract.lstrip("/")
    mine = (report.contract or "/ES").lstrip("/")
    direction = "higher" if report.basis > 0 else "lower"
    return (f"The letter is on {mine}; {other} trades {abs(report.basis):g} {direction}, "
            f"so on a {other} chart every level here reads {abs(report.basis):g} {direction}.")


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

    sym = report.contract or "/ES"
    lines.append(f"> {sym} five-minute candles, {report.window_start} → "
                 f"{report.window_end} ({report.candle_count} candles). "
                 f"Last price {report.last_close:g}. Same close-based "
                 "definitions as the chart renderer."
                 + (f" {basis_note(report)}" if basis_note(report) else ""))
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
                           tolerance: float = DEFAULT_TOLERANCE_PTS,
                           quote_fetch: Callable[..., dict[str, float]] | None = None,
                           ) -> OvernightReport:
    """Fetch → compute, as data. Never raises — errors land in ``report.error``.

    Split out of ``build_overnight_section`` for the refresh path [st-vxbw],
    which wants the counts (broken / reclaimed / held) for its terminal summary
    as well as the rendered block."""
    report = OvernightReport()
    try:
        start = letter_window_start(result.date)
        res = resolve_letter_contract(result, start, fetch=fetch, quote_fetch=quote_fetch)
        candles = res.candles
        report.contract = res.symbol
        report.resolution = res.reason
        report.basis = res.basis
        report.basis_contract = res.basis_contract
        report.candles = list(candles)
        report.interactions = compute_interactions(result.levels, candles,
                                                   tolerance)
        report.last_close = candles[-1]["close"]
        report.window_start = _fmt_ct(candles[0]["datetime"])
        report.window_end = _fmt_ct(candles[-1]["datetime"])
        report.candle_count = len(candles)
        logger.info("overnight contract: %s — %s%s", res.symbol, res.reason,
                    (f"; {res.basis_contract} basis {res.basis:+g}"
                     if res.basis is not None else ""))
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
