"""The letter measured against the tape. [st-7xzw]

Steve, 2026-09-14: the plan said "bulls keep full control while ~7620 holds"
after 7620 had already fallen overnight, and every note after it read as if
7620 were still the floor. "The process of parsing the doc uses the letter as
a starting point but measures everything against the reality of the overnight
price action."

``overnight.py`` already computes what happened to each ladder level. This
module turns that into two things the desk doc puts *above* the bias:

  1. a reality block — where price is on the letter's contract, which levels
     have been lost or reclaimed since he wrote, and whether the letter's own
     floor and bear trigger have already resolved;
  2. a status tag on every forward note, read off the states of the levels
     the note is anchored to.

The vocabulary is Mancini's own mechanics, stated as fact about the tape:

  VOID     a "must hold" support in a bull-case note closed through and has
           not been recovered — the note's premise is gone
  LIVE     a bear-case / breakdown note whose trigger price has been closed
           through; price is below it now
  ARMED    a Failed Breakdown / reclaim note whose support has been lost and
           not yet reclaimed — the loss has printed, the reclaim has not
  PRINTED  a Failed Breakdown note whose support broke and was reclaimed
  TRAPPED  a bear note whose trigger broke and was reclaimed (his "80% of
           breakdowns trap")
  TAGGED   a resistance in the note was poked and rejected
  CLEARED  a resistance in the note was closed above and held
  INTACT   a bull-case note whose supports have held (or trapped and
           recovered — his "quick trap below")
  AHEAD    nothing in the note has been touched yet
  (none)   an unconditional note

Nothing here is a recommendation. It restates his conditions against what
the candles did; the read is Steve's.
"""
from __future__ import annotations

from typing import Sequence

from . import schema
from .overnight import DEFAULT_TOLERANCE_PTS, LevelInteraction, OvernightReport, basis_note
from .schema import Commentary, ParseResult

BEAR_TAGS = {"bear_case", "breakdown_short", "short_entry"}
LONG_SETUP_TAGS = {"failed_breakdown", "level_reclaim", "backtest_long", "bid_direct", "long_entry"}
BULL_TAGS = {"bull_case", "summary", "breakout_target"}


def anchor_states(report: OvernightReport) -> dict[float, LevelInteraction]:
    return {it.price: it for it in report.interactions}


def _kind_of(price: float, result: ParseResult) -> str:
    for lv in result.levels:
        if lv.price == price:
            return lv.kind
    return ""


def _lost(it: LevelInteraction) -> bool:
    return it.state == "broken"


def _fmt_lost(it: LevelInteraction) -> str:
    ran = f", ran to {it.extreme:g}" if it.extreme is not None else ""
    return f"{it.price:g} lost {it.break_time}{ran}"


def _fmt_reclaimed(it: LevelInteraction) -> str:
    ran = f" (ran to {it.extreme:g})" if it.extreme is not None else ""
    return f"{it.price:g} broke {it.break_time}{ran}, reclaimed {it.reclaim_time}"


def _fmt_state(it: LevelInteraction) -> str:
    if it.state == "broken":
        return _fmt_lost(it)
    if it.state == "reclaimed":
        return _fmt_reclaimed(it)
    if it.state == "tested-held":
        return f"{it.price:g} tested, held ({it.defenses} defended)"
    return f"{it.price:g} untouched"


def _side(price: float, last: float | None) -> str:
    if last is None:
        return ""
    d = last - price
    return f"{abs(d):.2f} {'above' if d > 0 else 'below'}".replace(".00", "")


def note_status(c: Commentary, result: ParseResult, report: OvernightReport,
                ) -> tuple[str, str]:
    """(verdict, detail) for one forward note. Verdict "" for unconditional
    notes or when the report failed."""
    if report.error or c.trigger.type == "unconditional" or not c.trigger.anchor_prices:
        return "", ""
    states = anchor_states(report)
    last = report.last_close
    tags = set(c.tags or [])
    anchors = list(c.trigger.anchor_prices)
    sups = [p for p in anchors if _kind_of(p, result) == "support"]
    ress = [p for p in anchors if _kind_of(p, result) == "resistance"]
    trigs = [p for p in anchors if _kind_of(p, result) not in ("support", "resistance")]
    parts = [_fmt_state(states[p]) for p in anchors if p in states]
    for p in trigs:
        if last is not None:
            parts.append(f"{p:g} trigger — price {_side(p, last)}")
    detail = " · ".join(parts)

    sup_its = [states[p] for p in sups if p in states]
    res_its = [states[p] for p in ress if p in states]
    lost = [it for it in sup_its if _lost(it)]
    reclaimed = [it for it in sup_its if it.state == "reclaimed"]
    tagged = [it for it in res_its if it.state == "reclaimed"]
    cleared = [it for it in res_its if it.state == "broken"]

    bearish = bool(tags & BEAR_TAGS) and not (tags & {"bull_case"})
    # A bull-case or summary note is judged as a hold/target claim even when
    # it also names his Failed Breakdown — "hold 7620 or a quick trap below"
    # is about the floor, not an entry.
    long_setup = (bool(tags & LONG_SETUP_TAGS) and not bearish
                  and not (tags & {"bull_case", "summary"}))

    if bearish:
        floor = min(anchors)
        if ress and not sups:
            # short spots at resistance
            if tagged:
                return "TAGGED", detail
            if cleared:
                return "CLEARED", detail
            return "AHEAD", detail
        if lost and last is not None and last < floor:
            return "LIVE", detail
        if reclaimed and not lost:
            return "TRAPPED", detail
        if lost:
            return "LIVE", detail
        return "AHEAD", detail

    if long_setup:
        if lost:
            return "ARMED", detail
        if reclaimed:
            return "PRINTED", detail
        if any(it.state == "tested-held" for it in sup_its):
            return "TESTED", detail
        return "AHEAD", detail

    # bull case / summary / targets
    if lost:
        return "VOID", detail
    if ress and not sups:
        if cleared:
            return "CLEARED", detail
        if tagged:
            return "TAGGED", detail
        if c.trigger.type == "price_cross" and last is not None and last > min(ress):
            return "LIVE", detail
        return "AHEAD", detail
    if reclaimed:
        return "INTACT via trap", detail
    if any(it.state in ("tested-held", "reclaimed") for it in sup_its) or tagged or cleared:
        return "INTACT", detail
    return "AHEAD", detail


def annotate_notes(result: ParseResult, report: OvernightReport) -> list[str]:
    """Markdown bullets for the forward-notes section, each tagged."""
    lines: list[str] = []
    for c in result.commentary:
        anchors = ", ".join(str(p) for p in c.trigger.anchor_prices)
        suffix = f"  _[{c.trigger.type}: {anchors}]_" if anchors else f"  _[{c.trigger.type}]_"
        verdict, detail = note_status(c, result, report)
        if verdict:
            lines.append(f"- **{verdict}** — {c.text}{suffix}")
            if detail:
                lines.append(f"  - _{detail}_")
        else:
            lines.append(f"- {c.text}{suffix}")
    return lines


def _letter_floor(result: ParseResult) -> float | None:
    """The lowest support he ties the bull case to — his 'must hold'."""
    cands = []
    for c in result.commentary:
        tags = set(c.tags or [])
        if tags & {"bull_case", "summary"} and not tags & BEAR_TAGS:
            cands += [p for p in c.trigger.anchor_prices if _kind_of(p, result) == "support"]
    return min(cands) if cands else None


def _bear_trigger(result: ParseResult) -> float | None:
    cands = []
    for c in result.commentary:
        tags = set(c.tags or [])
        if tags & {"bear_case", "breakdown_short"}:
            cands += [p for p in c.trigger.anchor_prices]
    return max(cands) if cands else None


def render_reality_block(result: ParseResult, report: OvernightReport,
                         tolerance: float = DEFAULT_TOLERANCE_PTS) -> str:
    """The block that goes above the bias."""
    if report.error:
        return ("## Where price is against the letter\n\n"
                f"_Tape unavailable ({report.error}) — the bias and notes below "
                "are the letter as written, unmeasured._")
    last = report.last_close
    sym = (report.contract or "/ES").lstrip("/")
    lines = [f"## Where price is against the letter — {sym} {last:g} at {report.window_end}", ""]
    if report.resolution:
        lines.append(f"- Contract: {sym} — {report.resolution}."
                     + (f" {basis_note(report, tolerance)}" if basis_note(report, tolerance) else ""))

    its = report.interactions
    lost = sorted((it for it in its if it.kind == "support" and _lost(it)), key=lambda i: -i.price)
    lost_res = sorted((it for it in its if it.kind == "resistance" and _lost(it)), key=lambda i: i.price)
    fb = sorted((it for it in its if it.kind == "support" and it.state == "reclaimed"), key=lambda i: -i.price)
    rej = sorted((it for it in its if it.kind == "resistance" and it.state == "reclaimed"), key=lambda i: i.price)

    def _tier(it: LevelInteraction) -> str:
        return " major" if it.major else ""

    if lost:
        lines.append("- Supports lost since the letter (closed through, not recovered): "
                     + " · ".join(f"**{it.price:g}**{_tier(it)} ({it.break_time}"
                                  + (f", ran to {it.extreme:g}" if it.extreme is not None else "") + ")"
                                  for it in lost))
    if lost_res:
        lines.append("- Resistances cleared (closed above, holding): "
                     + " · ".join(f"**{it.price:g}**{_tier(it)} ({it.break_time})" for it in lost_res))
    if fb:
        lines.append("- Failed Breakdowns already printed (lost, then reclaimed): "
                     + " · ".join(f"{it.price:g}{_tier(it)} ({it.break_time} → {it.reclaim_time}"
                                  + (f", ran to {it.extreme:g}" if it.extreme is not None else "") + ")"
                                  for it in fb))
    if rej:
        lines.append("- Resistances poked and rejected: "
                     + " · ".join(f"{it.price:g}{_tier(it)} (to {it.extreme:g}, back under {it.reclaim_time})"
                                  if it.extreme is not None else f"{it.price:g}{_tier(it)}"
                                  for it in rej))
    if not (lost or lost_res or fb or rej):
        lines.append("- No ladder level has been closed through or reclaimed since the letter.")

    # Where price sits now, against the ladder as it stands (a lost support
    # above price is resistance until it reclaims — his own rule).
    below = [it for it in its if it.price < last]
    above = [it for it in its if it.price > last]
    if below:
        nb = max(below, key=lambda i: i.price)
        below_txt = f"{nb.price:g}{_tier(nb)} {nb.kind} ({_fmt_state(nb).split(' ', 1)[1]})"
    else:
        below_txt = "nothing on the ladder"
    if above:
        na = min(above, key=lambda i: i.price)
        flipped = " — a lost support, resistance until it reclaims" if (na.kind == "support" and _lost(na)) else ""
        above_txt = f"{na.price:g}{_tier(na)} {na.kind} ({_fmt_state(na).split(' ', 1)[1]}){flipped}"
    else:
        above_txt = "nothing on the ladder"
    lines.append(f"- Price now: {_side(nb.price, last) if below else 'above'} {below_txt}; "
                 f"{_side(na.price, last) if above else 'below'} {above_txt}.")

    states = anchor_states(report)
    floor = _letter_floor(result)
    if floor is not None and floor in states:
        it = states[floor]
        if _lost(it):
            verdict = (f"**BROKEN** — {_fmt_lost(it)}, not reclaimed. The bull-case branch as "
                       "written has lost its premise")
        elif it.state == "reclaimed":
            verdict = f"held via trap — {_fmt_reclaimed(it)} (his 'quick trap below')"
        elif it.state == "tested-held":
            verdict = f"holding — tested, {it.defenses} defended close{'s' if it.defenses != 1 else ''}"
        else:
            verdict = f"untouched — price {_side(floor, last)}"
        lines.append(f"- The letter's floor, {floor:g} (\"must hold\"): {verdict}.")
    trig = _bear_trigger(result)
    if trig is not None:
        if trig in states:
            it = states[trig]
            if _lost(it):
                bt = (f"**LIVE** since {it.break_time} — {_fmt_lost(it)}; price is "
                      f"{_side(trig, last)}")
            elif it.state == "reclaimed":
                bt = f"trapped — {_fmt_reclaimed(it)}"
            else:
                bt = f"not triggered — price {_side(trig, last)}"
        else:
            bt = (f"price {_side(trig, last)}"
                  + (" — **below the trigger**" if last is not None and last < trig else ""))
        lines.append(f"- The letter's bear trigger, below {trig:g}: {bt}.")
    lines.append("")
    lines.append("_The bias and notes below are the letter as written; each note carries "
                 "its state against the tape above._")
    return "\n".join(lines)
