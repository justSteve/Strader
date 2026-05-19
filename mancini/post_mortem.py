"""Generate post-mortem slides: prior forecast levels vs actual session action.

Each action slide from today's recap is annotated with the prior day's
forecast levels that were nearby, showing which held, broke, or were
never tested.
"""
from __future__ import annotations

from .parser import ManciniEmail, Slide, Level


def _nearby_levels(
    price: float,
    levels: list[Level],
    key_set: set[float],
    radius: float = 30.0,
) -> list[dict]:
    nearby = []
    for lv in levels:
        dist = abs(lv.price - price)
        if dist <= radius:
            nearby.append({
                "price": lv.price,
                "annotation": lv.annotation,
                "key": lv.price in key_set,
                "distance": round(dist, 1),
            })
    return sorted(nearby, key=lambda x: x["distance"])


def _level_tag(lv: dict, side: str) -> str:
    k = "K " if lv["key"] else ""
    maj = "*" if "major" in lv["annotation"] else ""
    return f"{k}{int(lv['price'])}{maj} {side}"


def render_post_mortem(
    prior: ManciniEmail,
    current: ManciniEmail,
    *,
    action_only: bool = True,
    radius: float = 40.0,
) -> str:
    """Render post-mortem slides comparing prior forecast vs current recap."""
    lines: list[str] = []
    lines.append(f"# Post-Mortem: {prior.date} Forecast vs {current.date} Action")
    lines.append(f"# Prior: {prior.subject}")
    lines.append(f"# Recap: {current.subject}")
    lines.append("")

    prior_key = set(prior.key_levels)

    prior_sup_sorted = sorted(prior.support_levels, key=lambda l: l.price, reverse=True)
    prior_res_sorted = sorted(prior.resistance_levels, key=lambda l: l.price)

    lines.append("## Prior Forecast Key Levels")
    lines.append("")
    keys_str = ", ".join(
        f"**{int(p)}**" for p in sorted(prior_key)
    )
    lines.append(f"  {keys_str}")
    lines.append("")
    lines.append("---")
    lines.append("")

    sections: dict[str, list[Slide]] = {}
    for s in current.slides:
        sections.setdefault(s.section, []).append(s)

    tested: set[float] = set()
    broke: set[float] = set()

    for sec_name, slides in sections.items():
        if action_only:
            slides = [s for s in slides if _is_action(s)]
        if not slides:
            continue

        lines.append(f"## {sec_name}")
        lines.append("")

        for slide in slides:
            anchor = slide.time_anchor or "      "
            badge = _dir_badge(slide.direction)

            prices_in_slide = slide.price_levels
            if not prices_in_slide:
                price_str = ""
                nearby_sup = []
                nearby_res = []
            else:
                price_str = " ".join(str(int(p)) for p in prices_in_slide)
                ref_price = prices_in_slide[0]
                nearby_sup = _nearby_levels(ref_price, prior_sup_sorted, prior_key, radius)
                nearby_res = _nearby_levels(ref_price, prior_res_sorted, prior_key, radius)

            header = f"  {anchor:>8}  {badge}"
            if price_str:
                header += f"  [{price_str}]"
            lines.append(header)

            text = slide.sentence.strip()
            wrapped = _wrap(text, indent=16, width=100)
            lines.append(wrapped)

            if nearby_sup or nearby_res:
                lines.append("")
                lines.append("                FORECAST LEVELS NEARBY:")
                for lv in nearby_sup[:4]:
                    hit = ""
                    for p in prices_in_slide:
                        if abs(p - lv["price"]) < 5:
                            hit = " <-- TESTED"
                            tested.add(lv["price"])
                            if slide.direction == "sell" and p < lv["price"]:
                                hit = " <-- BROKE"
                                broke.add(lv["price"])
                    lines.append(f"                  S  {_level_tag(lv, '')} ({lv['distance']:+.0f} pts){hit}")
                for lv in nearby_res[:4]:
                    hit = ""
                    for p in prices_in_slide:
                        if abs(p - lv["price"]) < 5:
                            hit = " <-- TESTED"
                            tested.add(lv["price"])
                            if slide.direction == "rip" and p > lv["price"]:
                                hit = " <-- CLEARED"
                    lines.append(f"                  R  {_level_tag(lv, '')} ({lv['distance']:+.0f} pts){hit}")

            lines.append("")

        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")

    all_prior = set(l.price for l in prior.support_levels + prior.resistance_levels)
    untested = sorted(all_prior - tested, reverse=True)

    lines.append(f"  Levels tested:   {len(tested)}/{len(all_prior)}")
    lines.append(f"  Levels broke:    {len(broke)} ({', '.join(str(int(p)) for p in sorted(broke))})" if broke else "  Levels broke:    0")
    lines.append(f"  Key levels hit:  {len(tested & prior_key)}/{len(prior_key)} ({', '.join(str(int(p)) for p in sorted(tested & prior_key))})" if tested & prior_key else f"  Key levels hit:  0/{len(prior_key)}")
    lines.append("")

    return "\n".join(lines)


_TEACHING = [
    "it took me years", "it doesnt matter if", "it doesn't matter if",
    "profitable trading looks like", "i do the same template",
    "i do this trade recap", "for one reason mostly", "new traders",
    "whole industry", "flipping back and forth",
]


def _is_action(slide: Slide) -> bool:
    lower = slide.sentence.lower()
    if any(p in lower for p in _TEACHING):
        return False
    return bool(slide.price_levels) or slide.direction in ("sell", "rip")


def _dir_badge(d: str) -> str:
    if d == "sell":
        return "SELL"
    if d == "rip":
        return " RIP"
    return "    "


def _wrap(text: str, indent: int, width: int) -> str:
    prefix = " " * indent
    words = text.split()
    out: list[str] = []
    cur = prefix
    for word in words:
        if len(cur) + 1 + len(word) > width and cur.strip():
            out.append(cur)
            cur = prefix + word
        else:
            cur = cur + " " + word if cur.strip() else prefix + word
    if cur.strip():
        out.append(cur)
    return "\n".join(out)
