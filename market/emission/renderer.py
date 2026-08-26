"""Render emission strings from the lexicon, so no surface hand-builds one.

Desk Ruling 1 item 5 (memo 20260825T143000, re-sequenced to lead by the 18:00
amendment): *emission strings are never hand-formatted; they render from a
mapping of field to canonical display name per surface, and the mapping lives
in the lexicon.* This module is that mapping's only consumer, and
``docs/lexicon/lexicon.yaml``'s ``emission:`` block is its only input.

WHAT IT PREVENTS. One number — the count of distinct prices a sweep's
aggressor walked — went by three words at once: the field said ``ticks_swept``,
the written line said "3 levels", the spoken line said "three ticks", and the
ratified word was a fourth thing, ``tick-level``. Nothing was broken and nobody
had lied; three surfaces had each been written by hand, months apart. A linter
finds that AFTER someone writes it wrong. A template that cannot contain a
field's name finds it never, because there is nowhere to write it.

THE SHAPE. A template holds slots and connective tissue. The word naming a
quantity lives once, in ``emission.quantities``, and every surface pulls it
from there. To give one number two words you would have to bind one field to
two quantities, and :func:`schema` refuses to load a lexicon that does.
Validation runs at load, not at call: Desk's stated principle behind this
ruling is point-of-write validation, arrived at after a ledger writer let a bad
value through because its check ran once the string was already built.

USE::

    from market.emission import render

    render("sweep-print", "reason", {
        "direction": "buy", "span": (7555.00, 7555.50),
        "ticks_swept": 3, "total_size": 49,
    })
    # 'buy sweep 7555.00->7555.50 (3 tick-levels, 49 contracts)'

Every failure is an :class:`EmissionError` naming the template, the surface and
the slot. None of them are user input — each one is a call site disagreeing
with the lexicon, which is a bug in exactly one of the two.

Bead: st-bkvt.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from market.emission.numbers import spoken_count, spoken_price

__all__ = [
    "render", "renders", "schema", "reload",
    "EmissionError", "SchemaError", "SlotError", "HindsightLeak",
]

ROOT = Path(__file__).resolve().parent.parent.parent
LEXICON_PATH = ROOT / "docs/lexicon/lexicon.yaml"

# {field}, {field:bare}, {@name}
_SLOT = re.compile(r"\{(@?[a-z_][a-z0-9_]*)(?::([a-z]+))?\}")

_MODIFIERS = frozenset({"bare"})
_KINDS = frozenset({"count", "price", "price-span", "enum"})


class EmissionError(Exception):
    """Base for every way an emission can fail to render."""


class SchemaError(EmissionError):
    """The lexicon's ``emission:`` block is internally inconsistent. Raised at
    load, so a broken lexicon fails the first import rather than the first
    emission — which, on a live tape, would be the worse of the two."""


class SlotError(EmissionError):
    """A call site and its template disagree: a missing value, an unexpected
    one, or a value the quantity's kind cannot render."""


class HindsightLeak(EmissionError):
    """A quantity knowable only after the session ends was about to reach a
    surface that speaks in real time. Ruling 8's fail-closed shape: anything
    whose ``live:`` is not exactly ``live`` is refused, including values
    invented after this code was written."""


# ── schema ─────────────────────────────────────────────────────────────────

_CACHE: dict | None = None


def reload() -> dict:
    """Drop the cached schema and re-read the lexicon. For tests and for the
    desk renderer; production reads the file once per process."""
    global _CACHE
    _CACHE = None
    return schema()


def schema() -> dict:
    """The validated ``emission:`` block, keyed for lookup.

    Returns a dict of ``surfaces``, ``names``, ``quantities`` (by id),
    ``by_field`` (``Signal.field`` -> quantity) and ``templates`` (by id).
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = _build(_load_raw())
    return _CACHE


def _load_raw() -> dict:
    doc = yaml.safe_load(LEXICON_PATH.read_text(encoding="utf-8"))
    block = doc.get("emission")
    if not block:
        raise SchemaError(
            f"{LEXICON_PATH} has no top-level `emission:` block. The renderer "
            "has no vocabulary without it; nothing can be emitted."
        )
    return block


def _build(block: dict) -> dict:
    surfaces = _keyed(block, "surfaces")
    names = _keyed(block, "names")
    quantities = _keyed(block, "quantities")
    templates = _keyed(block, "templates")

    for sid, s in surfaces.items():
        for f in ("numbers", "prices", "span_join", "sentence_case", "live_only"):
            if f not in s:
                raise SchemaError(f"surface {sid!r} is missing {f!r}")
        if s["numbers"] not in ("digits", "words"):
            raise SchemaError(f"surface {sid!r}: unknown numbers style {s['numbers']!r}")
        if s["prices"] not in ("decimal2", "spoken"):
            raise SchemaError(f"surface {sid!r}: unknown prices style {s['prices']!r}")

    # THE RULE that makes one number with two words unwritable: a field belongs
    # to at most one quantity. Everything else here is ordinary schema
    # hygiene; this line is the ruling.
    by_field: dict[str, dict] = {}
    for qid, q in quantities.items():
        if q.get("kind") not in _KINDS:
            raise SchemaError(f"quantity {qid!r}: unknown kind {q.get('kind')!r} "
                              f"(known: {', '.join(sorted(_KINDS))})")
        if q.get("live") is None:
            raise SchemaError(f"quantity {qid!r} is missing `live:`")
        if q["kind"] == "count" and not isinstance(q.get("display"), dict):
            raise SchemaError(f"quantity {qid!r} is a count and needs "
                              "`display: {one: ..., many: ...}`")
        if q["kind"] == "enum" and not isinstance(q.get("values"), dict):
            raise SchemaError(f"quantity {qid!r} is an enum and needs `values:`")
        for field in q.get("fields") or []:
            if "." not in field:
                raise SchemaError(
                    f"quantity {qid!r}: field {field!r} must be qualified as "
                    "`Signal.field` — `direction` and `price` recur across "
                    "signal types and a bare name silently merges them"
                )
            if field in by_field:
                raise SchemaError(
                    f"field {field!r} is bound to two quantities, {by_field[field]['id']!r} "
                    f"and {qid!r}. That is the defect this schema exists to make "
                    "unwritable — one number would carry two display words. Merge "
                    "them, or give the second one its own field."
                )
            by_field[field] = q

    for tid, t in templates.items():
        if t.get("name") and t["name"] not in names:
            raise SchemaError(f"template {tid!r} names {t['name']!r}, which is "
                              "not in `emission.names`")
        if not t.get("signal"):
            raise SchemaError(f"template {tid!r} is missing `signal:`")
        rendered = t.get("surfaces") or {}
        if not rendered:
            raise SchemaError(f"template {tid!r} renders to no surface at all")
        for sid, body in rendered.items():
            if sid not in surfaces:
                raise SchemaError(f"template {tid!r} renders to unknown surface {sid!r}")
            for slot, mod in _SLOT.findall(body):
                if mod and mod not in _MODIFIERS:
                    raise SchemaError(f"template {tid!r}/{sid}: unknown modifier "
                                      f"{mod!r} on {slot!r}")
                if slot.startswith("@"):
                    if slot != "@name":
                        raise SchemaError(f"template {tid!r}/{sid}: unknown "
                                          f"reference {slot!r}")
                    if not t.get("name"):
                        raise SchemaError(f"template {tid!r}/{sid} uses {{@name}} "
                                          "but the template has no `name:`")
                    continue
                qualified = f"{t['signal']}.{slot}"
                if qualified not in by_field:
                    raise SchemaError(
                        f"template {tid!r}/{sid}: slot {{{slot}}} resolves to "
                        f"{qualified!r}, which no quantity claims. Bind it in "
                        "`emission.quantities` — an unbound field has no "
                        "canonical word, which is the whole failure mode."
                    )

    return {"surfaces": surfaces, "names": names, "quantities": quantities,
            "by_field": by_field, "templates": templates}


def _keyed(block: dict, section: str) -> dict:
    rows = block.get(section)
    if not rows:
        raise SchemaError(f"`emission.{section}` is empty or missing")
    out: dict[str, dict] = {}
    for row in rows:
        rid = row.get("id")
        if not rid:
            raise SchemaError(f"a row in `emission.{section}` has no `id:`")
        if rid in out:
            raise SchemaError(f"`emission.{section}` has two rows with id {rid!r}")
        out[rid] = row
    return out


# ── rendering ──────────────────────────────────────────────────────────────

def renders(template_id: str, surface: str) -> bool:
    """Whether this emission has a rendering for this surface.

    A template with no entry for a surface is a deliberate silence — the
    written record carries things the spoken line should not, and the reverse.
    Ask this rather than catching the error.
    """
    sch = schema()
    tpl = sch["templates"].get(template_id)
    return bool(tpl and surface in (tpl.get("surfaces") or {}))


def render(template_id: str, surface: str, values: Mapping[str, Any]) -> str:
    """Render one emission for one surface.

    ``values`` is keyed by bare field name; the template's ``signal:`` supplies
    the qualifier. Every slot must have a value and every value must fill a
    slot — a value with nowhere to go is how a number quietly stops being
    emitted, so it is an error, not a shrug.
    """
    sch = schema()
    tpl = sch["templates"].get(template_id)
    if tpl is None:
        raise SlotError(f"no emission template {template_id!r} "
                        f"(known: {', '.join(sorted(sch['templates']))})")
    surf = sch["surfaces"].get(surface)
    if surf is None:
        raise SlotError(f"no emission surface {surface!r} "
                        f"(known: {', '.join(sorted(sch['surfaces']))})")
    body = (tpl.get("surfaces") or {}).get(surface)
    if body is None:
        raise SlotError(
            f"template {template_id!r} has no {surface!r} rendering. That is a "
            "declared silence in the lexicon, not an oversight — call "
            "renders() first if the caller can legitimately be unsure."
        )

    used: set[str] = set()

    def fill(m: re.Match) -> str:
        slot, mod = m.group(1), m.group(2)
        if slot == "@name":
            return sch["names"][tpl["name"]]["display"]
        used.add(slot)
        if slot not in values:
            raise SlotError(f"{template_id}/{surface}: no value for {{{slot}}}")
        qty = sch["by_field"][f"{tpl['signal']}.{slot}"]
        return _format(qty, values[slot], surf, mod, f"{template_id}/{surface}.{slot}")

    out = _SLOT.sub(fill, body)

    extra = set(values) - used
    if extra:
        raise SlotError(
            f"{template_id}/{surface}: {', '.join(sorted(extra))} passed but not "
            "in the template. A value with no slot is a number that silently "
            "stops being emitted — add the slot or drop the value."
        )

    if surf["sentence_case"]:
        out = _capitalize_first(out)
    return out


def _format(qty: dict, value: Any, surf: dict, mod: str | None, where: str) -> str:
    if surf["live_only"] and qty["live"] != "live":
        raise HindsightLeak(
            f"{where}: {qty['id']!r} is `live: {qty['live']}` and {surf['id']!r} "
            "speaks in real time. Refused rather than spoken — a hindsight "
            "quantity said live asserts something nobody can know yet."
        )

    kind = qty["kind"]
    if kind == "count":
        return _format_count(qty, value, surf, mod, where)
    if mod:
        raise SlotError(f"{where}: modifier {mod!r} means nothing on a {kind}")
    if kind == "price":
        return _format_price(_as_float(value, where), surf)
    if kind == "price-span":
        return _format_span(value, surf, where)
    if kind == "enum":
        return _format_enum(qty, value, where)
    raise SchemaError(f"{where}: unhandled kind {kind!r}")   # pragma: no cover


def _format_count(qty: dict, value: Any, surf: dict, mod: str | None, where: str) -> str:
    if qty.get("from") == "length":
        try:
            n = len(value)
        except TypeError:
            raise SlotError(f"{where}: {qty['id']!r} counts the length of its "
                            f"value, but {value!r} has no length") from None
    else:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SlotError(f"{where}: {qty['id']!r} is a count and wants an int, "
                            f"got {type(value).__name__} {value!r}")
        n = value

    num = str(n) if surf["numbers"] == "digits" else spoken_count(n)
    if mod == "bare":
        return num
    word = qty["display"]["one" if n == 1 else "many"]
    return f"{num} {word}"


def _format_price(value: float, surf: dict) -> str:
    return f"{value:.2f}" if surf["prices"] == "decimal2" else spoken_price(value)


def _format_span(value: Any, surf: dict, where: str) -> str:
    try:
        start, end = value
    except (TypeError, ValueError):
        raise SlotError(f"{where}: a price-span wants a (start, end) pair, "
                        f"got {value!r}") from None
    return (_format_price(_as_float(start, where), surf)
            + surf["span_join"]
            + _format_price(_as_float(end, where), surf))


def _format_enum(qty: dict, value: Any, where: str) -> str:
    try:
        return qty["values"][value]
    except (KeyError, TypeError):
        raise SlotError(
            f"{where}: {value!r} is not a member of {qty['id']!r} "
            f"(members: {', '.join(sorted(qty['values']))})"
        ) from None


def _as_float(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SlotError(f"{where}: wanted a price, got "
                        f"{type(value).__name__} {value!r}")
    return float(value)


def _capitalize_first(s: str) -> str:
    """Capitalize the first letter without touching the rest — ``str.capitalize``
    would lower-case everything after it, which eats acronyms and price words."""
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
    return s
