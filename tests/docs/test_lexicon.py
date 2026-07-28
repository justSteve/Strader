"""Lexicon integrity — structure + the compound-term convention. [st-g9y]

The CI seed for lexicon-as-code: a banned bare word appearing uncompounded
in any definition fails the suite. Hyphen-attached uses (flush-leg,
delta-flip) and uses inside another listed compound are legal.
"""
import re
from pathlib import Path

import yaml

LEX = Path(__file__).resolve().parent.parent.parent / "docs/lexicon/lexicon.yaml"


def _lexicon():
    return yaml.safe_load(LEX.read_text())


def test_loads_and_has_required_fields():
    lex = _lexicon()
    assert lex["meta"]["version"] >= 1
    assert lex["banned_bare"] and lex["terms"]
    for t in lex["terms"]:
        for f in ("term", "tier", "status", "live", "definition", "on_the_chart"):
            assert f in t, f"{t.get('term', '?')} missing {f}"


def test_no_banned_bare_word_in_definitions():
    lex = _lexicon()
    banned = [b["word"] for b in lex["banned_bare"]]
    offenders = []
    for t in lex["terms"]:
        text = f"{t['definition']} {t['on_the_chart']}"
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
