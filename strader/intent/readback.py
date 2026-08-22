"""The four-tier spoken read-back, and the direction-anchor echo. [st-79z.3]

Two renderings of the same plan: ``read_back`` for the eye (a few short lines) and
``spoken`` for the ear (TTS-safe: prices in trader words via the speech phrasebook,
abbreviations spelled out, one thought per sentence — feedback_mobile-spoken-style).

The echo is the mandatory guard from knowledge/direction-inversion-watch.md: before a
directional intent is accepted, the first move's direction is said out loud, then what a
setup of that kind usually pays, then what Steve said. If the two disagree the echo says
so plainly — and still lets him keep his call with a yes. External check, his decision.
"""
from __future__ import annotations

from present.speech import spoken_count, spoken_price
from strader.intent.entities import DayPlan, Intent, Level, Order, Regime, StructureTemplate

_SETUP_WORDS = {
    "failed_breakdown": "failed breakdown", "level_reclaim": "level reclaim",
    "failed_breakout": "failed breakout", "level_reject": "level reject",
    "flush_and_recover": "flush and recover", "v_down": "late flush and the V back",
    "clean_break": "clean break", "clean_reject": "clean reject", "breakdown_short": "breakdown short",
    "chop": "chop",
}
_WINDOW_WORDS = {"window-open": "the first hour", "window-midday": "midday", "window-late": "the late window"}
_EXPIRY_WORDS = {"0DTE": "expiring today", "1DTE": "expiring tomorrow", "2DTE": "expiring in two days"}
_VEHICLE_WORDS = {"fly": "fly", "single": "single", "vertical": "vertical", "condor": "condor"}


def spoken_frame(frame: str) -> str:
    return {"ES": "E S", "SPX": "S P X"}.get(frame, frame)


def say_price(p, frame: bool = True) -> str:
    s = spoken_price(p.value)
    return f"{s} {spoken_frame(p.frame)}" if frame else s


# ---------------------------------------------------------------- pieces

def level_line(lv: Level, speak: bool) -> str:
    px = say_price(lv.price) if speak else str(lv.price)
    if lv.price2:
        px += (" to " + (say_price(lv.price2, frame=False) if speak else f"{lv.price2.value:g}"))
    bits = [px]
    if lv.tier:
        bits.append(lv.tier)
    bits.append(lv.label if lv.label and lv.label != lv.kind else lv.kind)
    who = {"mancini": "Mancini", "carmine": "Carmine"}.get(lv.source, "")
    line = " ".join(bits) + (f", {who}'s" if who else "")
    if lv.state != "untouched":
        line += f" ({lv.state})"
    return line


def regime_line(r: Regime, speak: bool) -> str:
    parts = []
    if r.day_type:
        parts.append(f"Day type {r.day_type.replace('-', ' ') if speak else r.day_type}.")
    if r.control:
        side = "below" if r.control == "bears" else "above"
        if r.pivot:
            px = say_price(r.pivot) if speak else str(r.pivot)
            parts.append(f"{r.control.capitalize()} control {side} {px}.")
        else:
            parts.append(f"{r.control.capitalize()} control.")
    return " ".join(parts)


def anchor_echo(i: Intent, speak: bool = False) -> str:
    """The guard sentence. Always names the first move, then the payoff side, then the call."""
    if i.direction_anchor is None:
        return (f"I could not tell which way the first move goes in: \"{i.quote}\". "
                f"Say the flush direction first (for example: flush down, then long).")
    first = i.direction_anchor
    fam = i.setup.family if i.setup else "unknown"
    setup_word = _SETUP_WORDS.get(i.setup.name, i.setup.name) if i.setup else "this"
    if fam == "trap":
        pays = "up" if first == "down" else "down"
        rule = f"a {setup_word} after a move {first} is a trap, and the trap pays {pays}"
    elif fam == "continuation":
        pays = first
        rule = f"a {setup_word} pays with the move, {pays}"
    else:
        rule = f"I do not know which way a {setup_word} usually pays"
    said = f"you said {i.direction}"
    if i.looks_inverted:
        verdict = (f"That reads INVERTED: {rule}, which is a {i.expected_direction}, but {said}. "
                   f"Say yes to keep it as you said it, or no to drop it.")
    else:
        verdict = f"{rule}, and {said}. Say yes to arm it, or no."
    return f"First move {first}. " + verdict


def intent_line(i: Intent, speak: bool) -> str:
    cond = i.trigger.condition_text.strip().rstrip(".")
    setup = (" — " + _SETUP_WORDS.get(i.setup.name, i.setup.name)) if i.setup else ""
    anchor = f" (first move {i.direction_anchor}, pays {i.direction})" if i.direction_anchor else ""
    window = f", {_WINDOW_WORDS.get(i.window, i.window)}" if i.window else ""
    vehicle = f", {_VEHICLE_WORDS.get(i.vehicle_hint, i.vehicle_hint)}" if i.vehicle_hint else ""
    status = "armed" if i.confirmed else "NOT yet confirmed"
    line = f"{i.direction.upper()}{setup}{anchor}{window}{vehicle}: \"{cond}\" — {status}"
    if speak:
        line = (f"{i.direction}{setup}{anchor}{window}{vehicle}. {cond}. "
                f"{'Armed' if i.confirmed else 'Not yet confirmed'}.")
    return line


def structure_line(s: StructureTemplate, speak: bool) -> str:
    bits = [f"{s.lots} lot{'s' if s.lots != 1 else ''}" if not speak else
            f"{spoken_count(s.lots)} lot{'s' if s.lots != 1 else ''}",
            _VEHICLE_WORDS.get(s.vehicle, s.vehicle)]
    if s.width:
        bits.append(f"{spoken_count(s.width) if speak else s.width} wide")
    bits.append(_EXPIRY_WORDS.get(s.expiry, s.expiry) if speak else s.expiry)
    if s.right:
        bits.append("calls" if s.right == "CALL" else "puts")
    center = s.center
    if center == "ATM":
        bits.append("at the money")
    elif center.replace(".", "").isdigit():
        bits.append(f"centered on {spoken_price(float(center)) if speak else center}")
    else:
        bits.append(f"on the {center}")
    if s.delta_hint:
        bits.append(f"{s.delta_hint} delta" if s.delta_hint != "first-ITM" else "first strike in the money")
    return ", ".join(bits)


def order_line(o: Order, speak: bool) -> str:
    strikes = " / ".join((spoken_price(k, ) if speak else f"{k:g}") for k in o.strikes)
    px = f"{o.price:.2f}"
    if speak:
        cents = round(o.price * 100)
        px = (f"{spoken_count(cents // 100)} dollar{'s' if cents // 100 != 1 else ''} "
              f"{spoken_count(cents % 100)}" if cents >= 100 else f"{spoken_count(cents)} cents")
    qty = spoken_count(abs(o.quantity)) if speak else str(abs(o.quantity))
    kind = o.spread_type.lower() if o.spread_type != "SINGLE" else ("call" if o.right == "CALL" else "put")
    right = "" if o.spread_type == "SINGLE" else (" calls" if o.right == "CALL" else " puts")
    cost = f"{o.est_cost_usd:.0f} dollars total" if speak else f"${o.est_cost_usd:,.0f} total"
    return (f"{'Buying' if o.action == 'BUY' else 'Selling'} {qty} {kind}{right}, {strikes}, "
            f"{_EXPIRY_WORDS.get('0DTE') if speak and o.expiry else o.expiry.isoformat()}, "
            f"{px} {o.price_kind}, {cost}")


# ---------------------------------------------------------------- the read-back

def read_back(plan: DayPlan, speak: bool = False, notes: list[str] | None = None) -> str:
    """Four tiers, in order, then what was not understood. ``speak`` renders for the ear."""
    out: list[str] = []
    if plan.levels:
        frame_hint = f" ({spoken_frame(plan.frame_default) if speak else plan.frame_default} unless said)"
        items = "; ".join(level_line(lv, speak) for lv in plan.levels)
        out.append(f"Levels{frame_hint}: {items}.")
    if plan.regime.day_type or plan.regime.control:
        out.append(regime_line(plan.regime, speak))
    if plan.intents:
        out.append("Watching: " + (" ".join if speak else "; ".join)(intent_line(i, speak) for i in plan.intents)
                   + ("" if speak else "."))
    if plan.structures:
        out.append("Vehicle: " + "; ".join(structure_line(s, speak) for s in plan.structures) + ".")
    if plan.orders:
        out.append("Priced: " + "; ".join(order_line(o, speak) for o in plan.orders) + ".")
    if notes:
        out.append(("Frames: " if not speak else "On the numbers: ") + "; ".join(notes) + ".")
    if plan.unparsed:
        out.append("I did not understand: " + " | ".join(f"\"{u}\"" for u in plan.unparsed) + ".")
    if not out:
        out.append("Nothing on the plan yet.")
    return "\n".join(out)
