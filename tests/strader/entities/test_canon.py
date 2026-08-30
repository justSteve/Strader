"""The knowledge bundle read as data — strader/entities/canon.py. [st-k5a8]

Two kinds of test. The fixture bundles under tmp_path pin the header contract
(plan §2): what validates, what is refused and why, and what the loader derives
(cite ranges, statement, quote, admissibility). The last test loads the REAL
bundle and fails on any file that does not validate — the same discipline
``test_the_real_manifest_builds_and_its_pins_hold`` gives the manifest. It is
marked xfail(strict=True) until the header migration (st-ts3o) lands; when the
bundle validates it turns into an unexpected pass, which is the reminder to
remove the mark.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from strader.entities import canon
from strader.entities.canon import Canon, CanonError, Entity, load_entity

HEADER = """---
id: {id}
type: {type}
status: {status}
owner: Steve
provenance:
  origin: {origin}
  ref: "{ref}"
lineage:
  supersedes: {supersedes}
  since: 2026-08-30
  commit: {commit}
{extra}title: "{title}"
description: "A {type} for the tests."
timestamp: 2026-08-30T05:00:00-05:00
---
"""

BODY = """
# {title}

Intro line the excerpt must not include.

## Statement

Skip the trade or downgrade the expectation when a wall sits between
price and the target. Second sentence stays in the excerpt.

## Why

Because the wall absorbs the move.
"""


def write(dir_: Path, ident: str, *, type_="management-rule", status="trusted",
          origin="steve-dictation", ref="master reference §Risk rules", supersedes="null",
          commit="null", extra="", title=None, body=BODY, stem=None) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    title = title or ident.replace("-", " ").title()
    text = HEADER.format(id=ident, type=type_, status=status, origin=origin, ref=ref,
                         supersedes=supersedes, commit=commit, extra=extra, title=title)
    text += body.format(title=title)
    p = dir_ / f"{stem or ident}.md"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def bundle(tmp_path: Path) -> tuple[Path, Path]:
    k = tmp_path / "knowledge"
    pb = tmp_path / "strader" / "playbooks"
    write(k, "orb-target-1")
    write(k, "gex-sign-regime", type_="regime-rule")
    write(k, "srs-scalping", type_="setup", status="exploratory", origin="empirical-observation",
          ref="st-ylqw")
    write(k, "lvn-method", type_="concept", status="under-review", origin="third-party-source",
          ref="OFB-3")
    write(k, "counter-dictum", type_="decision", status="tabled", origin="steve-dictation",
          ref="st-k68o", body="\n# Charter\n\nDo not cite it.\n")
    write(k, "how-we-name-things", type_="convention", status="trusted", ref="co-czvg",
          body="\n# Naming\n\nOne concept per file.\n")
    (k / "index.md").write_text("---\ntype: convention\ntitle: Index\n---\n# Index\n")
    (k / "log.md").write_text("---\ntype: convention\ntitle: Log\n---\n# Log\n")
    write(k / "sources", "ofb-register", type_="register", status="source",
          origin="third-party-source", ref="Desk memo 2026-08-26",
          body="\n# Register\n\n- OFB-1 — absorption.\n")
    write(pb, "orb-playbook", type_="strategy", status="trusted", ref="InvestiTrade",
          extra="rules: [orb-target-1, gex-sign-regime]\ncode: ORB\nname: Opening Range Breakout\n",
          body="\n## Thesis\n\nThe first fifteen minutes.\n\n## Statement\n\nOne trade per morning.\n")
    return k, pb


# ─── what validates, and what the loader derives ─────────────────────────────

def test_a_conformant_bundle_loads_and_reserved_files_are_skipped(bundle):
    k, pb = bundle
    c = Canon.load((k, pb), repo_root=k.parent)
    assert len(c) == 8
    assert {p.name for p in c.reserved} == {"index.md", "log.md"}
    assert "orb-target-1" in c and "ofb-register" in c
    assert c.problems == {}


def test_admissible_is_method_type_with_an_admitting_status(bundle):
    k, pb = bundle
    c = Canon.load((k, pb), repo_root=k.parent)
    assert {e.id for e in c.admissible()} == {"orb-target-1", "gex-sign-regime",
                                              "srs-scalping", "orb-playbook"}
    # under-review, tabled, source and a convention all refuse
    assert not c.by_id("lvn-method").admissible
    assert not c.by_id("counter-dictum").admissible
    assert not c.by_id("ofb-register").admissible
    assert not c.by_id("how-we-name-things").admissible
    assert {e.id for e in c.by_status("exploratory")} == {"srs-scalping"}
    assert {e.id for e in c.by_type("register")} == {"ofb-register"}


def test_cite_ranges_statement_and_quote(bundle):
    k, pb = bundle
    e = load_entity(k / "orb-target-1.md")
    assert e.cite == ("## Statement",)
    [(start, end)] = e.cite_ranges()
    # line numbers are of the whole file, front matter included
    assert e.lines[start - 1].startswith("Skip the trade")
    assert e.lines[end - 1].endswith("stays in the excerpt.")
    assert "## Why" not in e.statement() and "Intro line" not in e.statement()
    assert e.quote() == ("Skip the trade or downgrade the expectation when a wall sits "
                         "between price and the target.")


def test_strategy_lists_its_rules_and_extra_keys_are_kept(bundle):
    k, pb = bundle
    c = Canon.load((k, pb), repo_root=k.parent)
    orb = c.by_id("orb-playbook")
    assert orb.rules == ("orb-target-1", "gex-sign-regime")
    assert orb.extra["code"] == "ORB" and orb.extra["name"] == "Opening Range Breakout"
    assert orb.since == date(2026, 8, 30) and orb.supersedes is None and orb.commit is None


def test_supersedes_resolves_to_an_id_or_a_path_heading(bundle, tmp_path):
    k, pb = bundle
    old = tmp_path / "docs" / "old-reference.md"
    old.parent.mkdir()
    old.write_text("# Old\n\n## Risk rules\n\ntext\n")
    write(k, "split-from-id", supersedes="orb-target-1")
    write(k, "split-from-file", supersedes='"docs/old-reference.md#Risk rules"')
    c = Canon.load((k, pb), repo_root=tmp_path)
    assert c.by_id("split-from-file").supersedes == "docs/old-reference.md#Risk rules"


# ─── what is refused ─────────────────────────────────────────────────────────

def problems_of(k: Path, pb: Path, name: str, root: Path | None = None) -> list[str]:
    c = Canon.load((k, pb), strict=False, repo_root=root or k.parent)
    hits = [msgs for p, msgs in c.problems.items() if p.name == f"{name}.md"]
    assert hits, f"{name} validated but should not have"
    return hits[0]


def test_id_must_equal_the_stem_and_be_kebab(bundle):
    k, pb = bundle
    write(k, "wrong-id", stem="right-stem")
    write(k, "Not_Kebab", stem="Not_Kebab")
    assert any("does not equal the file stem" in m for m in problems_of(k, pb, "right-stem"))
    assert any("not kebab-case" in m for m in problems_of(k, pb, "Not_Kebab"))


def test_closed_vocabularies_are_enforced(bundle):
    k, pb = bundle
    write(k, "bad-type", type_="kind")
    write(k, "bad-status", status="worthy")
    write(k, "bad-origin", origin="hearsay")
    assert any("type 'kind'" in m for m in problems_of(k, pb, "bad-type"))
    assert any("status 'worthy'" in m for m in problems_of(k, pb, "bad-status"))
    assert any("provenance.origin 'hearsay'" in m for m in problems_of(k, pb, "bad-origin"))


def test_letter_is_generated_only_and_source_is_for_registers(bundle):
    k, pb = bundle
    write(k, "letter-row", status="letter")
    write(k, "setup-as-source", type_="setup", status="source")
    write(k / "sources", "trusted-register", type_="register", status="trusted",
          body="\n# R\n\n- OFB-1.\n")
    assert any("generated-only" in m for m in problems_of(k, pb, "letter-row"))
    assert any("only for types" in m for m in problems_of(k, pb, "setup-as-source"))
    assert any("register carries status 'source'" in m
               for m in problems_of(k, pb, "trusted-register"))


def test_missing_fields_are_reported_together_with_the_path(bundle):
    k, pb = bundle
    p = k / "bare.md"
    p.write_text("---\ntype: setup\ntitle: Bare\n---\n\n## Statement\n\nx.\n")
    with pytest.raises(CanonError) as exc:
        load_entity(p)
    msg = str(exc.value)
    assert str(p) in msg
    assert "missing header field(s): id, status, owner, provenance, lineage, description, timestamp" in msg


def test_a_method_entity_needs_its_cite_heading(bundle):
    k, pb = bundle
    write(k, "no-statement", type_="concept", body="\n# C\n\n## Thesis\n\ntext\n")
    write(k, "named-cite", type_="concept", extra='cite: ["## Thesis", "## Missing"]\n',
          body="\n# C\n\n## Thesis\n\ntext\n")
    assert any("'## Statement' not found" in m for m in problems_of(k, pb, "no-statement"))
    assert any("'## Missing' not found" in m for m in problems_of(k, pb, "named-cite"))
    # a convention has no default cite and validates without a Statement
    e = load_entity(k / "how-we-name-things.md")
    assert e.cite == () and e.cite_ranges() == []


def test_rule_block_shape_and_rules_key_placement(bundle):
    k, pb = bundle
    write(k, "half-rule", type_="regime-rule",
          extra="rule:\n  registered: abc1234\n  module: rules/half-rule\n")
    write(k, "rules-on-a-setup", type_="setup", extra="rules: [orb-target-1]\n")
    assert any("rule block missing entry, exit, instrument" in m
               for m in problems_of(k, pb, "half-rule"))
    assert any("rules: is only for type 'strategy'" in m
               for m in problems_of(k, pb, "rules-on-a-setup"))


def test_catalog_level_problems_duplicates_and_unresolved_references(bundle, tmp_path):
    k, pb = bundle
    write(pb, "orb-target-1")                      # same id in the second directory
    write(k, "dangling", supersedes="no-such-entity")
    write(k, "dangling-file", supersedes='"docs/nope.md#Heading"')
    write(pb, "strategy-x", type_="strategy", ref="x", extra="rules: [ghost-rule]\n")
    c = Canon.load((k, pb), strict=False, repo_root=tmp_path)
    flat = [m for msgs in c.problems.values() for m in msgs]
    assert any("duplicate id 'orb-target-1'" in m for m in flat)
    assert any("neither an entity id nor 'path#heading'" in m for m in flat)
    assert any("docs/nope.md does not exist" in m for m in flat)
    assert any("rules entry 'ghost-rule' is not an entity id" in m for m in flat)
    # strict mode raises one error naming every offending file
    with pytest.raises(CanonError) as exc:
        Canon.load((k, pb), repo_root=tmp_path)
    assert "dangling.md" in str(exc.value) and "strategy-x.md" in str(exc.value)


def test_lineage_since_must_be_a_date_and_commit_a_sha(bundle):
    k, pb = bundle
    p = write(k, "bad-lineage", commit="notasha")
    p.write_text(p.read_text().replace("since: 2026-08-30", "since: soon"))
    msgs = problems_of(k, pb, "bad-lineage")
    assert any("lineage.since 'soon'" in m for m in msgs)
    assert any("lineage.commit 'notasha'" in m for m in msgs)


def test_cli_report_exits_nonzero_on_problems_and_lists_ids(bundle, capsys):
    k, pb = bundle
    assert canon.main(["--dir", str(k), "--dir", str(pb), "--ids"]) == 0
    out = capsys.readouterr().out
    assert "orb-target-1\tmanagement-rule\ttrusted" in out
    write(k, "broken", status="worthy")
    assert canon.main(["--dir", str(k), "--dir", str(pb), "--report"]) == 1
    out = capsys.readouterr().out
    assert "1 do not" in out and "broken.md" in out and "status 'worthy'" in out


# ─── the real bundle ─────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True,
                   reason="until the header migration lands (st-ts3o) the real bundle does not "
                          "carry the extended header; an unexpected pass means remove this mark")
def test_the_real_bundle_validates():
    c = Canon.load()
    assert len(c) >= 40          # 31 knowledge concepts + 9 playbook records, measured 2026-08-29
    assert {p.name for p in c.reserved} == {"index.md", "log.md"}
    assert c.problems == {}


def test_the_real_bundle_is_readable_in_report_mode():
    """Pre-migration the loader must still open every file and say what is missing."""
    c = Canon.load(strict=False)
    assert len(c.problems) + len(c) >= 40
    for path, msgs in c.problems.items():
        assert msgs, path
        assert not any("does not parse" in m for m in msgs), (path, msgs)
    assert isinstance(next(iter(c.problems.values()))[0], str) if c.problems else True
