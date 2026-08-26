"""The spoken surface's liveness guard, derived from the lexicon. [st-hd51]

Desk Ruling 8 (memo 20260826T001224__Desk__rulings-7-8-and-setupname): a
surface that speaks in real time says nothing whose ``live:`` is not exactly
``live``, and the hand-copied ``_HINDSIGHT_TOKENS`` denylist in
``present/speech.py`` is RETIRED rather than extended.

Ruling 7 closed the ``live:`` domain first, deliberately: honest members, then
an allowlist over them. ``tests/docs/test_lexicon.py`` guards the domain; this
file guards the consumer. The two failure modes it exists to catch are the two
that made the denylist unfixable — under-coverage (10 of 27 hindsight terms)
and substring collision (``leg`` inside *allege*, ``pace`` inside *space*).
"""
import re

import pytest
import yaml

from market.emission import renderer
from present import speech
from present.speech import HindsightLeak, speak
from market.signals.types import Bias


@pytest.fixture(autouse=True)
def _fresh_lexicon():
    """Each test reads the real file; anything that patches it puts it back."""
    renderer.reload()
    yield
    renderer.reload()


def _lexicon_terms():
    doc = yaml.safe_load(renderer.LEXICON_PATH.read_text(encoding="utf-8"))
    return doc["terms"]


# ── the derivation ─────────────────────────────────────────────────────────

def test_every_non_live_term_is_unspeakable():
    """Coverage is TOTAL by construction, not by list length.

    The retired denylist named 13 tokens and covered 10 of 27 hindsight terms.
    This asserts the property that made it replaceable: the guard's set IS the
    lexicon's non-live set, so a term added tomorrow is covered tomorrow with
    no edit here.
    """
    unspeakable = renderer.unspeakable()
    expected = {t["term"].lower(): t["live"]
                for t in _lexicon_terms() if t["live"] != "live"}
    assert unspeakable == expected
    assert unspeakable, "the lexicon has carried hindsight stamps since 07-28"


def test_no_live_term_is_refused():
    """The guard must not silence the vocabulary the surface exists to speak."""
    unspeakable = renderer.unspeakable()
    live = [t["term"] for t in _lexicon_terms() if t["live"] == "live"]
    assert live, "sanity: the lexicon has live terms"
    assert [t for t in live if t.lower() in unspeakable] == []


def test_definitional_is_refused_alongside_hindsight():
    """Ruling 8 fails closed against `definitional` too, not only `hindsight`.

    `cutpoint` is a property of the grading machinery. Speaking it mid-session
    is not a false claim about the tape the way a hindsight term is — it is
    refused because the rule is an ALLOWLIST on `live`, and a rule that
    enumerated what to refuse is the one that was just retired.
    """
    assert renderer.unspeakable().get("cutpoint") == "definitional"


def test_a_domain_value_invented_later_fails_closed(monkeypatch):
    """The clause Desk wrote for values that do not exist yet.

    A fourth `live:` value added without touching this consumer must become
    UNSPEAKABLE, not silently speakable. A denylist gets this backwards by
    construction: what it does not name, it permits.
    """
    monkeypatch.setattr(renderer, "_DOC", {
        "terms": [
            {"term": "widget", "live": "live"},
            {"term": "gizmo", "live": "someday-maybe"},
        ],
    })
    monkeypatch.setattr(renderer, "_UNSPEAKABLE", None)
    unspeakable = renderer.unspeakable()
    assert unspeakable == {"gizmo": "someday-maybe"}
    with pytest.raises(HindsightLeak, match="someday-maybe"):
        renderer.assert_speakable("A gizmo appeared.", "test")
    renderer.assert_speakable("A widget appeared.", "test")


def test_an_empty_unspeakable_set_is_a_schema_error(monkeypatch):
    """Silence is the dangerous failure: a lexicon that yields no non-live
    terms means the file changed shape and the guard just became a no-op."""
    monkeypatch.setattr(renderer, "_DOC", {"terms": [{"term": "x", "live": "live"}]})
    monkeypatch.setattr(renderer, "_UNSPEAKABLE", None)
    with pytest.raises(renderer.SchemaError, match="lost its guard"):
        renderer.unspeakable()


# ── the substring collisions that made a denylist unfixable ────────────────

@pytest.mark.parametrize("line", [
    "The allegation is unproven.",          # 'leg' inside allege/allegation
    "There is space above.",                # 'pace' inside space
    "Spaced out, and pacing.",              # both, suffixed
    "Legacy levels from yesterday.",        # 'leg' prefixing another word
    "Give back nothing.",                   # 'giveback' only as one word
])
def test_a_term_fused_into_another_word_is_not_a_hit(line):
    """Desk's own two examples, plus the shapes around them. These are why
    'just add the missing 17' breaks the module while looking obvious."""
    renderer.assert_speakable(line, "test")


@pytest.mark.parametrize("line,term", [
    ("Buy flush-leg forming.", "flush-leg"),          # was in the hand copy
    ("The leg is extending.", "leg"),                 # bare, was NOT
    ("Pace picked up.", "pace"),                      # was NOT
    ("Graded F1 conviction here.", "F1 conviction"),  # multi-word, was NOT
    ("That is a graded-atom read.", "graded-atom"),   # Ruling 7's new term
])
def test_a_bare_non_live_term_is_refused(line, term):
    with pytest.raises(HindsightLeak) as exc:
        renderer.assert_speakable(line, "test")
    assert term.lower() in str(exc.value).lower()


def test_the_longest_matching_term_is_the_one_reported():
    """`band` and `coin-flip band` are both non-live. The message has to name
    the term that is actually there, or it sends the reader to the wrong
    lexicon entry."""
    with pytest.raises(HindsightLeak) as exc:
        renderer.assert_speakable("A coin-flip band call.", "test")
    assert "coin-flip band" in str(exc.value)


def test_the_message_names_the_caller_and_the_stamp():
    with pytest.raises(HindsightLeak) as exc:
        renderer.assert_speakable("A probe-fade.", "_bias phrasing")
    msg = str(exc.value)
    assert "_bias phrasing" in msg and "live: hindsight" in msg


# ── the consumer ───────────────────────────────────────────────────────────

def test_speech_and_renderer_raise_the_same_class():
    """One HindsightLeak, not two. A caller guarding a spoken emission should
    not have to know whether the schema path or a hand-built phrasing produced
    the leak — before st-hd51 these were different classes with the same name
    and different base classes."""
    assert speech.HindsightLeak is renderer.HindsightLeak


def test_speech_no_longer_carries_a_copy_of_the_vocabulary():
    """The retirement itself. A reinstated local list would pass every
    behavioural test above while re-creating the defect."""
    assert not hasattr(speech, "_HINDSIGHT_TOKENS")
    src = (renderer.ROOT / "present/speech.py").read_text(encoding="utf-8")
    terms = [t["term"] for t in _lexicon_terms() if t["live"] != "live"]
    quoted = [t for t in terms
              if re.search(rf'["\']{re.escape(t)}["\']', src)]
    assert not quoted, (
        f"present/speech.py quotes lexicon terms it must not carry: {quoted}")


def test_speak_refuses_a_phrasing_that_leaks(monkeypatch):
    """The end-to-end path, on a term the RETIRED list did not contain — the
    regression that matters is under-coverage, not the tokens it already had."""
    monkeypatch.setattr(speech, "_bias", lambda s: "Bias is bullish, host-leg agrees.")
    monkeypatch.setattr(speech, "_PHRASINGS", ((Bias, speech._bias),))
    sig = Bias(timestamp=0.0, source="test", confidence=0.8,
               reason="harness vocabulary", direction="bullish")
    with pytest.raises(HindsightLeak, match="host-leg"):
        speak(sig)


def test_the_live_phrasings_all_pass_the_guard():
    """Standing check that the widened net did not silence the surface: every
    string the module can emit is scanned against the derived set. This is the
    measurement that cleared the widening from 13 tokens to the full set."""
    import ast
    src = (renderer.ROOT / "present/speech.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Docstrings are documentation, not emissions — and this module's own
    # docstring necessarily discusses the terms it refuses. Same exclusion
    # tests/docs/test_lexicon.py makes at its emission sites, for the same
    # reason: scanning prose about a rule as though it were an instance of the
    # rule is how a linter earns its way onto an xfail list.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))

    lines = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            lines.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            lines.append("".join(
                str(v.value) if isinstance(v, ast.Constant) else "X"
                for v in node.values))
    assert lines, "sanity: speech.py has strings"
    for line in lines:
        renderer.assert_speakable(line, "static scan")
