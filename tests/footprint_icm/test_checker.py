"""The checker, with the trial's two planted bad examples. [st-h0xx]

Stop condition 1: the planted bad examples must fail by code before any
prompt exists. The first is the withdrawn 2026-08-25 phrasing hung on the
GEX-sign row; the second is the uncited generalisation that replaced it in
the runbook, hung on the Target-1 row. Neither row contains those words.
"""
import json
from datetime import date
from pathlib import Path

import pytest

import checker
import common
import excerpts

DAY = date(2026, 8, 27)


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    import common as c
    state = tmp_path_factory.mktemp("state")
    old = c.STATE
    c.STATE = state
    try:
        excerpts.build(DAY)
        ctx = c.run_dir(DAY) / "20-classify/context"
        return checker.load_context(ctx)
    finally:
        c.STATE = old


BAD_1 = 'LABEL 09:31 failed_breakdown regime=rotation cite=orb-gex-sign because="fade/skip context per the playbook"'
BAD_2 = 'IMPLICATION 09:31 cite=orb-target-1 because="management and expectancy, not its validity" text="Regime changes management, not validity."'
GOOD = 'IMPLICATION 09:31 cite=orb-target-1 because="skip the trade or downgrade the expectation" text="A GEX wall between price and the target means downgrade the expectation."'


def test_the_two_planted_bad_examples_fail_and_the_good_one_passes(context):
    v = checker.check_lines([BAD_1, BAD_2, GOOD], context)
    assert not v["ok"]
    assert [f["line_no"] for f in v["failures"]] == [1, 2]
    assert "not in orb-gex-sign word for word" in v["failures"][0]["reason"]
    assert "not in orb-target-1 word for word" in v["failures"][1]["reason"]
    assert v["counts"] == {"LABEL": 1, "IMPLICATION": 2, "CLAIM": 0}


def test_verbatim_survives_emphasis_line_breaks_and_case(context):
    line = ('LABEL 10:35 none regime=unstated cite=tsf-ceiling because="Trades tell us where '
            'aggression happened, not who is still holding or where anyone\'s stop sits"')
    assert checker.check_lines([line], context)["ok"]
    line2 = 'LABEL 10:35 none regime=trending cite=orb-gex-sign because="negative (trending regime) favors it"'
    assert checker.check_lines([line2], context)["ok"]


def test_unsourced_and_no_rule_lines_must_stand_alone(context):
    ok = ['LABEL 12:47 level_reject regime=unstated cite=UNSOURCED',
          'IMPLICATION 12:47 cite=NO-RULE-IN-CANON text="Canon has no management rule for rotation."']
    assert checker.check_lines(ok, context)["ok"]
    assert checker.check_lines(ok, context)["unsourced"] == 2
    bad = ['LABEL 12:47 level_reject regime=unstated cite=UNSOURCED because="fade the edge"']
    v = checker.check_lines(bad, context)
    assert not v["ok"] and "must stand alone" in v["failures"][0]["reason"]


def test_unknown_cite_missing_because_and_bad_vocabulary(context):
    v = checker.check_lines([
        'LABEL 12:47 level_reject regime=unstated cite=orb-rotation-rule because="fade"',
        'LABEL 12:47 level_reject regime=unstated cite=orb-target-1',
        'LABEL 12:47 breakout regime=chop cite=UNSOURCED',
        'something the model felt like saying',
    ], context)
    reasons = [f["reason"] for f in v["failures"]]
    assert any("not in the context index" in r for r in reasons)
    assert any("without because" in r for r in reasons)
    assert any("is not one of" in r and "breakout" in r for r in reasons)
    assert any("regime 'chop'" in r for r in reasons)
    assert any("matches no line shape" in r for r in reasons)


def test_claims_quote_the_live_reply_word_for_word(context):
    live = "The playbook's entry is the reclaim, trigger above 7666 — **fade/skip** context here."
    lines = [
        'CLAIM 12:47 kind=rule quote="fade/skip context here" cite=UNSOURCED',
        'CLAIM 12:47 kind=implication quote="trigger above 7666" cite=orb-target-1 because="Take Target 1 and walk away"',
        'CLAIM 12:47 kind=number quote="trigger above 7777" cite=UNSOURCED',
    ]
    v = checker.check_lines(lines, context, live)
    assert [f["line_no"] for f in v["failures"]] == [3]
    assert "not in the reply word for word" in v["failures"][0]["reason"]
    v2 = checker.check_lines(lines[:1], context, live=None)
    assert not v2["ok"] and "needs the live reply" in v2["failures"][0]["reason"]


def test_blank_lines_and_comments_are_allowed(context):
    assert checker.check_lines(["", "# no setups fired", "   "], context)["ok"]


def test_cli_writes_check_json_and_exits_2_on_failure(context, tmp_path, state_dir):
    excerpts.build(DAY)
    ctx = common.run_dir(DAY) / "20-classify/context"
    out = tmp_path / "output.md"
    out.write_text(BAD_1 + "\n" + GOOD + "\n")
    rc = checker.main([str(out), "--context", str(ctx)])
    assert rc == 2
    doc = json.loads((tmp_path / "check.json").read_text())
    assert doc["ok"] is False and len(doc["failures"]) == 1
    out.write_text(GOOD + "\n")
    assert checker.main([str(out), "--context", str(ctx)]) == 0


def test_a_required_line_type_that_never_appears_fails_on_line_0(context):
    """[st-k75z] an empty, refused or truncated reply used to pass as a clean
    run with zero labels — ``ok`` was ``not failures`` and nothing else."""
    for out in ([], ["", "# nothing fired"], ["   "]):
        v = checker.check_lines(out, context, require="LABEL")
        assert not v["ok"]
        assert len(v["failures"]) == 1
        assert v["failures"][0]["line_no"] == 0 and "no LABEL line" in v["failures"][0]["reason"]
    # an IMPLICATION-only output does not satisfy a LABEL requirement
    v = checker.check_lines([GOOD], context, require="LABEL")
    assert not v["ok"] and v["counts"] == {"LABEL": 0, "IMPLICATION": 1, "CLAIM": 0}
    # present -> clean; nothing required -> a quiet slice may legitimately be empty
    assert checker.check_lines(['LABEL 12:47 level_reject regime=unstated cite=UNSOURCED'],
                               context, require="LABEL")["ok"]
    assert checker.check_lines([], context)["ok"]
    with pytest.raises(common.LaneError, match="require='BOGUS'"):
        checker.check_lines([], context, require="BOGUS")


def test_cli_require_flag_exits_2_on_a_missing_line_type(context, tmp_path, state_dir):
    excerpts.build(DAY)
    ctx = common.run_dir(DAY) / "20-classify/context"
    out = tmp_path / "output.md"
    out.write_text(GOOD + "\n")
    assert checker.main([str(out), "--context", str(ctx)]) == 0
    assert checker.main([str(out), "--context", str(ctx), "--require", "CLAIM"]) == 2
    doc = json.loads((tmp_path / "check.json").read_text())
    assert doc["failures"][0]["line_no"] == 0 and "no CLAIM line" in doc["failures"][0]["reason"]
