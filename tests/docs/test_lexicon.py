"""Lexicon integrity — structure + the compound-term convention. [st-g9y]

The CI seed for lexicon-as-code: a banned bare word appearing uncompounded
in any definition fails the suite. Hyphen-attached uses (flush-leg,
delta-flip) and uses inside another listed compound are legal.

Extended [st-g9y] to two more lexicon surfaces:
  * drill/narrative accounts (docs/drills/day-in-fundamental-units-*.md)
  * code emissions — the human-readable reason/why/label strings the
    recognizer, day-type classifier, session recorder, and drill glosses
    emit (static scan of string literals at the emission sites).
Same fused-word regex discipline as the definition test; policy comes from
lexicon.yaml's own banned_bare + compounds data, nothing invented here.
"""
import ast
import re

import pytest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
LEX = ROOT / "docs/lexicon/lexicon.yaml"


def _lexicon():
    return yaml.safe_load(LEX.read_text())


def test_loads_and_has_required_fields():
    """Field policy comes from meta.term_fields, not from a constant here —
    the same discipline the banned-bare tests follow. [st-zt9b]"""
    lex = _lexicon()
    assert lex["meta"]["version"] >= 1
    assert lex["banned_bare"] and lex["terms"]
    required = lex["meta"]["term_fields"]["required"]
    for t in lex["terms"]:
        for f in required:
            assert f in t, f"{t.get('term', '?')} missing {f}"


def test_no_term_carries_an_unknown_field():
    """required + optional is the WHOLE field set. A misspelled key (`notes:`
    for `note:`) is otherwise invisible — YAML accepts it and every consumer
    silently ignores it. [st-zt9b]"""
    lex = _lexicon()
    fields = lex["meta"]["term_fields"]
    known = set(fields["required"]) | set(fields["optional"])
    offenders = [f"{t['term']}: unknown field {k!r}"
                 for t in lex["terms"] for k in t if k not in known]
    assert not offenders, "\n".join(offenders)


def test_live_domain_is_closed():
    """Desk Ruling 7, 2026-08-26: the `live:` domain is exactly the three
    members meta.live_domain names. A dual-natured term is SPLIT into two
    entries (raw-atom / graded-atom), never given a fourth token — one term
    carrying two meanings is the defect the whole vocabulary review is about.

    This is the domain half of the ruling; the consumer half is st-hd51,
    where speech.py speaks nothing whose value is not exactly `live`. Order is
    deliberate: honest members first, allowlist over them second. [st-zt9b]"""
    lex = _lexicon()
    domain = set(lex["meta"]["live_domain"])
    assert domain == {"live", "hindsight", "definitional"}, (
        f"the closed domain moved without a ruling: {sorted(domain)}")
    offenders = [f"{t['term']}: live: {t['live']!r}"
                 for t in lex["terms"] if t["live"] not in domain]
    assert not offenders, (
        f"{len(offenders)} term(s) outside the closed live: domain "
        f"{sorted(domain)}:\n" + "\n".join(offenders))


def test_no_banned_bare_word_in_definitions():
    lex = _lexicon()
    banned = [b["word"] for b in lex["banned_bare"]]
    offenders = []
    for t in lex["terms"]:
        text = f"{t['definition']} {t['on_the_chart']} {t.get('note', '')}"
        for w in banned:
            # bare = the word with no hyphen fused on either side
            for m in re.finditer(rf'(?i)(?<![\w"-]){re.escape(w)}(?![\w"-])', text):
                # "moves.jsonl" filename mention is exempt by rule
                ctx = text[max(0, m.start() - 8):m.end() + 8]
                if w == "move" and "moves.jsonl" in text:
                    continue
                offenders.append(f"{t['term']}: bare '{w}' in ...{ctx}...")
    assert not offenders, "\n".join(offenders)


def test_terms_are_unique():
    lex = _lexicon()
    names = [t["term"] for t in lex["terms"]]
    assert len(names) == len(set(names))


# ── banned-bare scanning, shared by the surface + emission linters ──────────

def _banned_words():
    return [b["word"] for b in _lexicon()["banned_bare"]]


def _bare_hits(text, banned):
    """Yield (word, context) for banned words appearing bare in ``text``.

    Same fused-word discipline as the definition test: an occurrence fused to
    a hyphen, a double-quote, or another word character (flush-leg, "flush",
    flushed, level_reclaim) is legal. The only data-driven exemption is the
    one lexicon.yaml itself notes: moves.jsonl keeps its filename.
    """
    for w in banned:
        for m in re.finditer(rf'(?i)(?<![\w"-]){re.escape(w)}(?![\w"-])', text):
            ctx = text[max(0, m.start() - 30):m.end() + 30]
            if w == "move" and "moves.jsonl" in ctx:
                continue
            yield w, ctx


# ── drill / narrative surfaces ──────────────────────────────────────────────

DRILL_ACCOUNT_GLOB = "docs/drills/day-in-fundamental-units-*.md"


@pytest.mark.xfail(
    strict=False,
    reason="st-g9y open rulings: 7/22 account's own bare-'trap'/'boundary' prose "
    "(shipped content, editorial pass pending) and quoted absorption.py emission "
    "strings ('absorbed, level broke') whose bare 'level' originates upstream. "
    "Remove this mark when the rulings land.",
)
def test_no_banned_bare_word_in_drill_accounts():
    """The measured-narrative accounts are lexicon surfaces: banned words
    appear only compounded. Quoted spans are NOT exempt — lexicon.yaml's
    conventions declare no quoting exemption, so a bare banned word inside a
    quoted letter passage flags like any other (the regex's quote-adjacency
    allowance, e.g. the single word "flush", is the only concession, same as
    the definition test)."""
    docs = sorted(ROOT.glob(DRILL_ACCOUNT_GLOB))
    assert docs, f"no drill accounts matched {DRILL_ACCOUNT_GLOB}"
    banned = _banned_words()
    offenders = []
    for doc in docs:
        rel = doc.relative_to(ROOT)
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for w, ctx in _bare_hits(line, banned):
                offenders.append(f"{rel}:{n}: bare '{w}' in ...{ctx.strip()}...")
    assert not offenders, (
        f"{len(offenders)} bare banned word(s) on drill surfaces:\n"
        + "\n".join(offenders))


# ── code emissions ──────────────────────────────────────────────────────────
# The human-readable strings the stack emits are lexicon surfaces too:
# SetupRecognition.reason (recognizer), DayType why (tpo), record labels
# (session_record), and the drill's per-beat teaching glosses (anatomy).
# Static scan of string literals at each emission site; to cover a new site,
# add a (file, kind, spec) row:
#   "function"    — every string literal inside the named def (docstring
#                   excluded: documentation, not an emission)
#   "dict_values" — string values of the named top-level dict assignment
#   "regex"       — group(1) of each match of the pattern over raw source
EMISSION_SITES = [
    # SetupRecognition.reason: state words, ACCEPT-branch text, f-string parts
    ("market/orderflow/recognizer.py", "function", "_emit"),
    # beat tokens surface verbatim in reason via "+".join(eng.beats)
    ("market/orderflow/recognizer.py", "regex",
     r'(?:\.beats\.append\(|self\.beats: list\[str\] = \[)"([a-z]+)"'),
    # DayType why strings
    ("market/orderflow/tpo.py", "function", "classify_day_type"),
    # replay-record labels + classify-failure fallback
    ("market/orderflow/session_record.py", "function", "record_day"),
    # drill teaching gloss shown as each beat fires
    ("market/orderflow/anatomy.py", "dict_values", "BEAT_GLOSS"),
]


def _function_strings(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            doc = None
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                doc = node.body[0].value
            for c in ast.walk(node):
                if (isinstance(c, ast.Constant) and isinstance(c.value, str)
                        and c is not doc):
                    yield c.lineno, c.value
            return
    raise AssertionError(f"emission site vanished: no def {name}()")


def _dict_value_strings(tree, name):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
                and any(isinstance(t, ast.Name) and t.id == name
                        for t in node.targets)):
            for v in node.value.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    yield v.lineno, v.value
            return
    raise AssertionError(f"emission site vanished: no dict {name} = {{...}}")


def _emission_strings():
    """(relpath, lineno, literal) for every string at every emission site."""
    for rel, kind, spec in EMISSION_SITES:
        src = (ROOT / rel).read_text(encoding="utf-8")
        if kind == "regex":
            found = [(src[:m.start()].count("\n") + 1, m.group(1))
                     for m in re.finditer(spec, src)]
        else:
            tree = ast.parse(src)
            found = list(_function_strings(tree, spec) if kind == "function"
                         else _dict_value_strings(tree, spec))
        assert found, f"emission site produced no strings: {rel} {kind} {spec}"
        for lineno, s in found:
            yield rel, lineno, s


@pytest.mark.xfail(
    strict=False,
    reason="st-g9y open ruling: beat enum tokens (flush/stall/flip/confirm) are the "
    "SetupRecognition.beats data contract frozen into append-only replay records — "
    "renaming to *-stage forms is a schema migration needing a ruling; plus "
    "anatomy.py's 'the trap is set' gloss needs editorial rewording.",
)
def test_no_banned_bare_word_in_code_emissions():
    banned = _banned_words()
    offenders = []
    for rel, lineno, s in _emission_strings():
        for w, _ in _bare_hits(s, banned):
            offenders.append(f"{rel}:{lineno}: bare '{w}' in emission {s!r}")
    assert not offenders, (
        f"{len(offenders)} bare banned word(s) in code emissions:\n"
        + "\n".join(offenders))
