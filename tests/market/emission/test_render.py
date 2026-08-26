"""The emission renderer: what it produces, and what it refuses. [st-bkvt]

The refusals matter more than the renderings here. This module exists so that
a class of mistake — one number wearing two words on two surfaces — becomes
unwritable rather than merely detectable, and every test below that asserts an
exception is asserting one edge of that.

Schema-shape tests build their own minimal `emission:` blocks rather than
leaning on the real lexicon: they are about the validator, and pinning them to
the live vocabulary would make an unrelated ruling turn them red.
"""
import re
import textwrap

import pytest
import yaml

from market.emission import renderer as R
from market.emission.renderer import (
    HindsightLeak, SchemaError, SlotError, render, renders, schema,
)

# The renderer's own slot pattern, so these tests cannot drift from what it
# actually strips when it renders.
_SLOT_RE = R._SLOT


# ── against the real lexicon ────────────────────────────────────────────────

def test_the_real_lexicon_validates():
    """Every guarantee below rests on the live `emission:` block loading. If
    this fails, read the SchemaError — it names the row."""
    s = schema()
    assert s["templates"] and s["quantities"] and s["surfaces"]


def test_sweep_reason_and_speech_use_the_same_word_for_the_same_field():
    """The bead in one assertion. `ticks_swept` was "levels" written and
    "ticks" spoken; the ratified word is tick-level and now both must carry
    it, because neither template can spell it."""
    written = render("sweep-print", "reason", {
        "direction": "buy", "span": (7555.00, 7555.50),
        "ticks_swept": 3, "total_size": 49,
    })
    spoken = render("sweep-print", "speech", {
        "direction": "buy", "ticks_swept": 3,
        "end_price": 7555.50, "total_size": 49,
    })
    assert "tick-level" in written and "tick-level" in spoken
    # Bare-word matching, the same fused-word discipline the lexicon's own
    # linter uses: "levels" inside "tick-levels" is the compound doing its job,
    # not the banned word returning.
    for stale in ("levels", "level", "ticks", "tick"):
        pattern = rf"(?<![\w-]){stale}(?![\w-])"
        assert not re.search(pattern, written), f"bare {stale!r} in {written!r}"
        assert not re.search(pattern, spoken), f"bare {stale!r} in {spoken!r}"


def test_sweep_reason_is_the_documented_string():
    assert render("sweep-print", "reason", {
        "direction": "buy", "span": (7555.00, 7555.50),
        "ticks_swept": 3, "total_size": 49,
    }) == "buy sweep 7555.00->7555.50 (3 tick-levels, 49 contracts)"


def test_sweep_speech_is_the_documented_string():
    assert render("sweep-print", "speech", {
        "direction": "buy", "ticks_swept": 8,
        "end_price": 7438.0, "total_size": 412,
    }) == ("Buy sweep, eight tick-levels through to seventy-four thirty-eight, "
           "four hundred twelve contracts.")


def test_counts_of_one_take_the_singular():
    assert "1 tick-level," in render("sweep-print", "reason", {
        "direction": "sell", "span": (7555.00, 7555.00),
        "ticks_swept": 1, "total_size": 1,
    })


def test_renders_reports_declared_silence_without_raising():
    assert renders("sweep-print", "speech")
    assert not renders("sweep-print", "nowhere")


# ── the call site and the template must agree ───────────────────────────────

def test_missing_value_is_an_error_not_an_empty_slot():
    with pytest.raises(SlotError, match="no value for {total_size}"):
        render("sweep-print", "reason", {
            "direction": "buy", "span": (1.0, 2.0), "ticks_swept": 3,
        })


def test_value_with_no_slot_is_an_error():
    """A number passed but not rendered is a number that silently stopped
    being emitted — the failure mode nobody notices for a month."""
    with pytest.raises(SlotError, match="passed but not in the template"):
        render("sweep-print", "speech", {
            "direction": "buy", "ticks_swept": 3, "end_price": 1.0,
            "total_size": 9, "start_price": 0.0,
        })


def test_unknown_template_names_the_known_ones():
    with pytest.raises(SlotError, match="sweep-print"):
        render("no-such-emission", "reason", {})


def test_unknown_surface_is_refused():
    with pytest.raises(SlotError, match="no emission surface"):
        render("sweep-print", "billboard", {"direction": "buy"})


def test_enum_member_outside_the_declared_set():
    with pytest.raises(SlotError, match="not a member of 'aggressor-side'"):
        render("sweep-print", "speech", {
            "direction": "sideways", "ticks_swept": 3,
            "end_price": 1.0, "total_size": 9,
        })


def test_count_wants_an_int():
    with pytest.raises(SlotError, match="wants an int"):
        render("sweep-print", "speech", {
            "direction": "buy", "ticks_swept": 3.5,
            "end_price": 1.0, "total_size": 9,
        })


def test_bool_is_not_an_int_here():
    """`True` is an int in Python and would render as "1 tick-level". It is a
    call-site bug every time, so it is refused rather than counted."""
    with pytest.raises(SlotError, match="wants an int"):
        render("sweep-print", "speech", {
            "direction": "buy", "ticks_swept": True,
            "end_price": 1.0, "total_size": 9,
        })


def test_span_wants_a_pair():
    with pytest.raises(SlotError, match="wants a \\(start, end\\) pair"):
        render("sweep-print", "reason", {
            "direction": "buy", "span": 7555.0,
            "ticks_swept": 3, "total_size": 9,
        })


# ── schema validation ───────────────────────────────────────────────────────

# A WHOLE stub lexicon, not an `emission:` fragment. The `terms:` and
# `banned_bare:` stanzas are here because renderer.py has a second reader over
# this same file — `_unspeakable()`, which derives the spoken surface's
# allowlist from the term list (st-hd51). A stub carrying only `emission:`
# still passes every test in this module, because none of them speak. But the
# first test that used this fixture and then called speak() would get
# "the file or its `live:` field changed shape" when the truth is "this stub
# has no term list" — a real error message misdiagnosing a fake lexicon.
# Cheaper to make the stub whole than to make the message hedge.
_MINIMAL = """
terms:
  - term: widget-gauge
    tier: axis
    status: ratified
    live: live
    definition: A live thing, so the guard lets it be spoken.
    on_the_chart: Nothing — this lexicon is a test stub.
  - term: widget-grade
    tier: band
    status: ratified
    live: hindsight
    definition: A hindsight thing, so `_unspeakable()` has something to find.
    on_the_chart: Nothing — this lexicon is a test stub.
emission:
  surfaces:
    - id: reason
      numbers: digits
      prices: decimal2
      span_join: "->"
      sentence_case: false
      live_only: false
    - id: speech
      numbers: words
      prices: spoken
      span_join: " to "
      sentence_case: true
      live_only: true
  names:
    - id: thing
      display: thing
  quantities:
    - id: widget
      kind: count
      live: live
      display: {one: widget, many: widgets}
      fields: [Demo.n]
  templates:
    - id: demo
      signal: Demo
      name: thing
      surfaces:
        reason: "{@name}: {n}"
        speech: "{@name}: {n}."
"""


@pytest.fixture
def lexicon(tmp_path, monkeypatch):
    """Point the renderer at a throwaway lexicon and restore the real one."""
    def _write(text):
        p = tmp_path / "lexicon.yaml"
        p.write_text(textwrap.dedent(text), encoding="utf-8")
        monkeypatch.setattr(R, "LEXICON_PATH", p)
        return R.reload()
    yield _write
    monkeypatch.undo()
    R.reload()


def test_minimal_schema_round_trips(lexicon):
    lexicon(_MINIMAL)
    assert render("demo", "reason", {"n": 2}) == "thing: 2 widgets"
    assert render("demo", "speech", {"n": 2}) == "Thing: two widgets."


def test_one_field_in_two_quantities_is_refused(lexicon):
    """THE RULE. Two quantities claiming one field is how a number would come
    to have two display words, so the lexicon does not load at all."""
    doubled = _MINIMAL.replace(
        "  templates:",
        "    - id: gadget\n"
        "      kind: count\n"
        "      live: live\n"
        "      display: {one: gadget, many: gadgets}\n"
        "      fields: [Demo.n]\n"
        "  templates:",
    )
    with pytest.raises(SchemaError, match="bound to two quantities"):
        lexicon(doubled)


def test_a_slot_no_quantity_claims_is_refused(lexicon):
    with pytest.raises(SchemaError, match="which no quantity claims"):
        lexicon(_MINIMAL.replace('reason: "{@name}: {n}"',
                                 'reason: "{@name}: {n} {unclaimed}"'))


def test_bare_field_name_is_refused(lexicon):
    """`direction` and `price` recur across signal types; an unqualified
    binding would silently merge two different quantities into one word."""
    with pytest.raises(SchemaError, match="must be qualified"):
        lexicon(_MINIMAL.replace("fields: [Demo.n]", "fields: [n]"))


def test_template_naming_an_undeclared_name_is_refused(lexicon):
    with pytest.raises(SchemaError, match="not in `emission.names`"):
        lexicon(_MINIMAL.replace("name: thing\n      surfaces",
                                 "name: nonesuch\n      surfaces"))


def test_template_rendering_to_an_unknown_surface_is_refused(lexicon):
    with pytest.raises(SchemaError, match="unknown surface"):
        lexicon(_MINIMAL.replace('speech: "{@name}: {n}."',
                                 'telegram: "{@name}: {n}."'))


def test_unknown_modifier_is_refused(lexicon):
    with pytest.raises(SchemaError, match="unknown modifier"):
        lexicon(_MINIMAL.replace("{n}", "{n:shouty}", 1))


def test_duplicate_ids_are_refused(lexicon):
    with pytest.raises(SchemaError, match="two rows with id"):
        lexicon(_MINIMAL.replace(
            "  templates:",
            "    - id: widget\n"
            "      kind: count\n"
            "      live: live\n"
            "      display: {one: w, many: w}\n"
            "      fields: [Demo.other]\n"
            "  templates:",
        ))


def test_a_lexicon_with_no_emission_block_is_refused(lexicon):
    with pytest.raises(SchemaError, match="no top-level `emission:` block"):
        lexicon("terms: []\n")


def test_the_stub_lexicon_is_whole_enough_for_the_other_reader(lexicon):
    """`renderer.py` has two readers over one file — the `emission:` block and
    `_unspeakable()`'s derivation from `terms:` (st-hd51). This fixture's stub
    must satisfy both, or a future test that uses it and then speaks gets a
    real error message describing a fake problem. Pinned so the `terms:`
    stanza cannot be tidied out of _MINIMAL as unused."""
    lexicon(_MINIMAL)
    assert R.unspeakable() == {"widget-grade": "hindsight"}
    R.assert_speakable("a widget-gauge is live and may be said", "stub")
    with pytest.raises(HindsightLeak):
        R.assert_speakable("a widget-grade may not", "stub")


# ── the live guard (Ruling 8's shape, at the point of write) ────────────────

_HINDSIGHT = _MINIMAL.replace("      live: live\n", "      live: hindsight\n")


def test_a_hindsight_quantity_cannot_reach_a_speaking_surface(lexicon):
    lexicon(_HINDSIGHT)
    with pytest.raises(HindsightLeak, match="speaks in real time"):
        render("demo", "speech", {"n": 2})


def test_the_same_quantity_may_be_written(lexicon):
    """The written record legitimately carries hindsight quantities — the
    postmortem is made of them. Only the speaking surface fails closed."""
    lexicon(_HINDSIGHT)
    assert render("demo", "reason", {"n": 2}) == "thing: 2 widgets"


def test_the_guard_fails_closed_on_a_value_invented_later(lexicon):
    """Ruling 8 is an allowlist, not a denylist: `live` passes and everything
    else is refused, including a value nobody has thought of yet."""
    lexicon(_MINIMAL.replace("      live: live\n", "      live: provisional\n"))
    with pytest.raises(HindsightLeak):
        render("demo", "speech", {"n": 2})


# ── formatting details ──────────────────────────────────────────────────────

def test_bare_modifier_drops_the_word(lexicon):
    lexicon(_MINIMAL.replace('reason: "{@name}: {n}"', 'reason: "{@name}: {n:bare}"'))
    assert render("demo", "reason", {"n": 2}) == "thing: 2"


def test_length_counts_the_value(lexicon):
    lexicon(_MINIMAL.replace("      kind: count\n",
                             "      kind: count\n      from: length\n"))
    assert render("demo", "reason", {"n": (1.0, 2.0, 3.0)}) == "thing: 3 widgets"


def test_sentence_case_capitalizes_the_first_letter_only(lexicon):
    """`str.capitalize` would lower-case the rest, eating acronyms."""
    lexicon(_MINIMAL.replace('speech: "{@name}: {n}."', 'speech: "{@name} ES: {n}."'))
    assert render("demo", "speech", {"n": 2}) == "Thing ES: two widgets."


def test_asking_for_a_surface_a_template_declines_points_at_renders(lexicon):
    lexicon(_MINIMAL.replace('    speech: "{@name}: {n}."\n', ""))
    with pytest.raises(SlotError, match=r"renders\(\)"):
        render("demo", "speech", {"n": 2})


# ── the templates themselves are a lexicon surface ──────────────────────────
# These two are the reason the mechanism holds rather than merely being
# intended. They live here, beside the renderer, rather than in
# tests/docs/test_lexicon.py: that file lints PROSE — definitions, drill
# accounts, hand-built emission strings — against banned_bare, while these
# lint the SCHEMA against itself. Splitting them would put the emission
# block's invariants somewhere the emission code does not have to pass.

def _templates():
    for tid, t in schema()["templates"].items():
        for sid, body in (t.get("surfaces") or {}).items():
            yield tid, sid, body


def test_no_template_contains_a_field_display_word():
    """THE MECHANISM, asserted. A template holds slots and connective tissue.
    The moment one spells a quantity's word — "3 tick-levels" written out
    instead of "{ticks_swept}" — that surface owns a second copy of the word
    and the two can drift, which is the whole defect back again."""
    words = set()
    for q in schema()["quantities"].values():
        words.update((q.get("display") or {}).values())
        words.update((q.get("values") or {}).values())

    offenders = []
    for tid, sid, body in _templates():
        outside = _SLOT_RE.sub(" ", body).lower()
        for w in words:
            if re.search(rf"(?<![\w-]){re.escape(w.lower())}(?![\w-])", outside):
                offenders.append(f"{tid}/{sid}: writes {w!r} instead of a slot")
    assert not offenders, (
        "a template names a quantity instead of slotting it:\n" + "\n".join(offenders))


def test_no_template_contains_a_banned_bare_word():
    """The 07-28 ban applies to templates like any other emission surface —
    more so, since a template is every future instance of that emission at
    once. This is the check that would have caught "N levels" at the source."""
    lex = yaml.safe_load(R.LEXICON_PATH.read_text(encoding="utf-8"))
    banned = [b["word"] for b in lex["banned_bare"]]
    offenders = []
    for tid, sid, body in _templates():
        outside = _SLOT_RE.sub(" ", body)
        for w in banned:
            if re.search(rf'(?i)(?<![\w"-]){re.escape(w)}(?![\w"-])', outside):
                offenders.append(f"{tid}/{sid}: bare {w!r} in {body!r}")
    assert not offenders, (
        "banned bare word in an emission template:\n" + "\n".join(offenders))


def test_every_declared_name_and_quantity_is_reachable():
    """Dead schema rows are how a lexicon starts describing a system that no
    longer exists. A quantity with no template is legal — it is a ratified
    word waiting for its emission, and it must say so in a `note:`. A NAME
    with no template is not: a name exists only to be rendered."""
    s = schema()
    used_names = {t["name"] for t in s["templates"].values() if t.get("name")}
    assert set(s["names"]) == used_names, (
        f"names declared but never rendered: {sorted(set(s['names']) - used_names)}")

    slotted = set()
    for tid, _, body in _templates():
        signal = s["templates"][tid]["signal"]
        slotted.update(f"{signal}.{slot}" for slot, _ in _SLOT_RE.findall(body)
                       if not slot.startswith("@"))
    for qid, q in s["quantities"].items():
        if not (set(q.get("fields") or []) & slotted):
            assert q.get("note"), (
                f"quantity {qid!r} is bound to no rendered slot and carries no "
                "`note:` saying why it is waiting")
