"""The rule registry: the real one validates and reproduces the 08-29 fire sets;
a broken one says what is wrong, naming the file. [st-djb9]"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from strader.blotter import rules as R
from strader.blotter.rules import RULES_DIR, RegistryError, load_rules, registry_problems
from strader.entities.canon import Canon, REPO_ROOT

LENS_ROWS = REPO_ROOT / "data" / "measurement" / "final-hour-lens-2026-08-29.jsonl"

ENTITY = """---
id: {id}
type: setup
status: exploratory
owner: Steve
provenance:
  origin: empirical-observation
  ref: "a test"
lineage:
  supersedes: null
  since: 2026-09-11
  commit: null
cite: ["## Statement"]
rule:
  registered: {registered}
  module: {module}
  entry: "when the test says so"
  exit:
    stop_pts: 0.30
    target_pct: 25
    time: "15:00 CT"
  instrument: {instrument}
title: "T"
description: "d"
timestamp: 2026-09-11T10:00:00-05:00
---

## Statement

A test rule.
"""

MODULE = '''
ID = "{id}"
STATE = "final-hour-lens"
FIRE_AT = ("14:45",)

def call(state):
    return "up" if state.get("fp", {{}}).get("pos", 0) >= 0.5 else None
'''


def _bundle(tmp_path: Path, entities: dict[str, dict], modules: dict[str, str]) -> tuple[Path, Path]:
    kdir = tmp_path / "knowledge"
    rdir = tmp_path / "rules"
    kdir.mkdir(parents=True)
    rdir.mkdir(parents=True)
    for ident, kw in entities.items():
        (kdir / f"{ident}.md").write_text(ENTITY.format(
            id=ident, registered=kw.get("registered", "abc1234"),
            module=kw.get("module", f"rules/{ident}"), instrument=kw.get("instrument", "itm-single-10")))
    for name, text in modules.items():
        (rdir / f"{name}.py").write_text(text)
    return kdir, rdir


# ─── the real registry ───────────────────────────────────────────────────────

def test_the_real_registry_validates():
    assert registry_problems() == []
    rules = load_rules()
    ids = [r.id for r in rules]
    assert ids == ["footprint-up-1445", "launch-into-no-lid-1445"]
    for r in rules:
        assert r.fire_at == ("14:45",)
        assert r.instrument == "itm-single-10"
        assert r.offset_spx == 10
        assert r.exit.stop_pts == 0.30 and r.exit.target_pct == 25 and r.exit.time_ct == "15:00"
        assert r.entity.status == "exploratory" and r.entity.type == "setup"


def test_every_rules_file_has_an_entity_and_the_reverse():
    canon = Canon.load(strict=False)
    with_rule = {e.id for e in canon.all() if e.rule is not None}
    files = {p.stem for p in RULES_DIR.glob("*.py") if not p.name.startswith("_")}
    assert with_rule == files


def test_registered_shas_are_ancestors_of_head():
    try:
        subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    for r in load_rules():
        rc = subprocess.run(["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", r.registered, "HEAD"]).returncode
        assert rc == 0, f"{r.id}: registered {r.registered} is not on this branch"


@pytest.mark.skipif(not LENS_ROWS.exists(), reason="the 08-29 lens rows are not on this box")
def test_the_rules_reproduce_the_0829_fire_sets():
    """footprint-up at 14:45 fired on 40 days, R2 on 26 (docs/measurement/
    final-hour-{lens-calls,combos}-2026-08-29.md); the ported rules must fire
    on exactly those days when handed the same rows (outcome stripped)."""
    rows = [json.loads(l) for l in open(LENS_ROWS)]
    rows = [r for r in rows if "skip" not in r and r.get("fp") and r["T"] == "1445"]
    rules = {r.id: r for r in load_rules()}
    visible = [{k: v for k, v in r.items() if k != "out"} for r in rows]
    fp_up = sorted(r["day"] for r in rows if r["fp"]["call"] == "up")
    got = sorted(r["day"] for r in visible if rules["footprint-up-1445"].call(r) == "up")
    assert got == fp_up and len(got) == 40
    r2 = sorted(r["day"] for r in rows
                if r["fp"]["pos"] >= 0.75 and r["fp"]["l30_chg"] > 0 and r["fp"]["l30_delta"] > 0
                and not (r.get("mc") or {}).get("lid"))
    got2 = sorted(r["day"] for r in visible if rules["launch-into-no-lid-1445"].call(r) == "up")
    assert got2 == r2 and len(got2) == 26


def test_rules_never_see_the_outcome():
    """The state handed to a rule carries no ``out`` group; the rule modules
    read fp/mc only. A rule that reaches for ``out`` gets None."""
    for r in load_rules():
        state = {"day": "2026-01-01", "T": "1445", "pT": 1.0,
                 "fp": {"pos": 0.9, "l30_chg": 1.0, "l30_delta": 5}, "mc": None, "gx": None}
        assert "out" not in state
        assert r.call(state) == "up"
        assert r.call({"fp": None}) is None
        assert r.call({}) is None


def test_lid_blocks_the_launch_and_not_the_footprint():
    rules = {r.id: r for r in load_rules()}
    state = {"fp": {"pos": 0.9, "l30_chg": 1.0, "l30_delta": 5}, "mc": {"lid": 7000.0}}
    assert rules["launch-into-no-lid-1445"].call(state) is None
    assert rules["footprint-up-1445"].call(state) == "up"
    state["mc"] = {"lid": None}
    assert rules["launch-into-no-lid-1445"].call(state) == "up"
    # the two thresholds differ: 0.75 fires R2, not the footprint's 0.80
    state = {"fp": {"pos": 0.77, "l30_chg": 1.0, "l30_delta": 5}, "mc": None}
    assert rules["launch-into-no-lid-1445"].call(state) == "up"
    assert rules["footprint-up-1445"].call(state) is None


# ─── a synthetic registry ────────────────────────────────────────────────────

def test_a_good_synthetic_registry_loads(tmp_path):
    kdir, rdir = _bundle(tmp_path, {"t-rule": {}}, {"t-rule": MODULE.format(id="t-rule")})
    assert registry_problems(dirs=(kdir,), rules_dir=rdir) == []
    rules = load_rules(dirs=(kdir,), rules_dir=rdir)
    assert [r.id for r in rules] == ["t-rule"]
    assert rules[0].call({"fp": {"pos": 0.6}}) == "up"
    assert load_rules(dirs=(kdir,), rules_dir=rdir, only="t-rule")[0].id == "t-rule"
    with pytest.raises(RegistryError):
        load_rules(dirs=(kdir,), rules_dir=rdir, only="nope")


def test_missing_module_file_is_named(tmp_path):
    kdir, rdir = _bundle(tmp_path, {"t-rule": {}}, {})
    probs = registry_problems(dirs=(kdir,), rules_dir=rdir)
    assert len(probs) == 1 and "t-rule.md" in probs[0] and "does not exist" in probs[0]
    with pytest.raises(RegistryError):
        load_rules(dirs=(kdir,), rules_dir=rdir)


def test_orphan_rules_file_is_named(tmp_path):
    kdir, rdir = _bundle(tmp_path, {}, {"orphan": MODULE.format(id="orphan")})
    probs = registry_problems(dirs=(kdir,), rules_dir=rdir)
    assert probs == ["orphan.py: no entity with id 'orphan' in the bundle"]


def test_module_id_mismatch_and_bad_instrument_and_bad_sha(tmp_path):
    kdir, rdir = _bundle(tmp_path, {"t-rule": {"instrument": "fly", "registered": "not-a-sha"}},
                         {"t-rule": MODULE.format(id="other")})
    probs = registry_problems(dirs=(kdir,), rules_dir=rdir)
    text = "\n".join(probs)
    assert "rule.instrument 'fly'" in text
    assert "rule.registered 'not-a-sha'" in text
    assert "ID 'other' != entity id 't-rule'" in text


def test_module_missing_names_and_bad_state(tmp_path):
    kdir, rdir = _bundle(tmp_path, {"t-rule": {}}, {"t-rule": "def call(s):\n    return None\n"})
    probs = registry_problems(dirs=(kdir,), rules_dir=rdir)
    assert any("lacks ID" in p for p in probs) and any("lacks FIRE_AT" in p for p in probs)
    kdir, rdir = _bundle(tmp_path / "b", {"t-rule": {}},
                         {"t-rule": MODULE.format(id="t-rule").replace("final-hour-lens", "something-else")})
    probs = registry_problems(dirs=(kdir,), rules_dir=rdir)
    assert any("STATE 'something-else'" in p for p in probs)


def test_module_that_does_not_import_is_a_problem_not_a_crash(tmp_path):
    kdir, rdir = _bundle(tmp_path, {"t-rule": {}}, {"t-rule": "this is not python\n"})
    probs = registry_problems(dirs=(kdir,), rules_dir=rdir)
    assert len(probs) == 1 and "does not import" in probs[0]


def test_a_rule_returning_a_wrong_word_is_refused(tmp_path):
    kdir, rdir = _bundle(tmp_path, {"t-rule": {}},
                         {"t-rule": MODULE.format(id="t-rule").replace('"up"', '"sideways"')})
    rule = load_rules(dirs=(kdir,), rules_dir=rdir)[0]
    with pytest.raises(RegistryError):
        rule.call({"fp": {"pos": 0.9}})


def test_exit_spec_parses_time_with_or_without_ct():
    assert R.ExitSpec.parse({"stop_pts": "0.3", "target_pct": 25, "time": "15:00 CT"}).time_ct == "15:00"
    assert R.ExitSpec.parse({"stop_pts": 0.3, "target_pct": 25, "time": "14:59"}).time_ct == "14:59"
    with pytest.raises(ValueError):
        R.ExitSpec.parse({"stop_pts": 0.3, "target_pct": 25, "time": "three"})
