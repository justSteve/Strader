"""The classify and claims drivers, and the classes, with the model stubbed. [st-h0xx]

``ICM_RUN_STAGE`` points the drivers at a shell script that writes output.md
and usage.json from a canned table keyed on the stage folder's name, so the
whole pipeline from slices to page runs without a model call. The checker
still runs for real against the real source list.
"""
import json
import os
import textwrap
from datetime import date
from pathlib import Path

import pytest

import checker
import claims
import classify
import common
import compare
import excerpts

DAY = date(2026, 8, 27)
A1 = "12:47 CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7747  anchor=resistance  from=below  close=7745.75  vol=1808  delta=+148"
A2 = "13:00 CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7745  anchor=resistance  from=below  close=7743.75  vol=2251  delta=+175"
BAR1 = "12:47 CT  F2 (developing, n=768) absorption  ES o7745.75 h7747.5 l7745.75 c7745.75  vol 1808 d+148"
BAR2 = "13:00 CT  F2 (developing, n=781) absorption  ES o7743.75 h7745.5 l7743.5 c7743.75  vol 2251 d+175"

CANNED = {
    "wake-1247": 'LABEL 12:47 level_reject regime=unstated cite=recognizer-setups because="failed_breakout / level_reject, the short"\n'
                 'IMPLICATION 12:47 cite=NO-RULE-IN-CANON text="The sources hold no management rule for a rejection at resistance."\n',
    "wake-1300": 'LABEL 12:47 level_reject regime=unstated cite=recognizer-setups because="failed_breakout / level_reject, the short"\n'
                 'LABEL 13:00 none regime=unstated cite=UNSOURCED\n',
    "window": 'LABEL 12:47 level_reject regime=unstated cite=recognizer-setups because="failed_breakout / level_reject, the short"\n'
              'LABEL 13:00 none regime=unstated cite=UNSOURCED\n'
              'LABEL 14:59 none regime=unstated cite=UNSOURCED\n',
    "claims": 'CLAIM 12:47 kind=setup quote="a clean rejection at 7747" cite=UNSOURCED\n'
              'CLAIM 12:47 kind=rule quote="rejections at resistance in a range are fade context" cite=UNSOURCED\n'
              'CLAIM 12:47 kind=regime quote="in a range" cite=UNSOURCED\n'
              'CLAIM 13:00 kind=setup quote="a failed breakdown at 7745" cite=UNSOURCED\n',
    "planted": 'CLAIM 09:31 kind=setup quote="It met every mechanical failed-breakdown criterion" cite=UNSOURCED\n'
               'CLAIM 09:31 kind=rule quote="with fade/skip context per the playbook" cite=UNSOURCED\n'
               'CLAIM 09:31 kind=rule quote="regime changes a setup\'s management and expectancy, not its validity" cite=UNSOURCED\n'
               'CLAIM 09:31 kind=implication quote="skip the trade or downgrade the expectation" cite=orb-target-1 because="skip the trade or downgrade the expectation"\n',
}


@pytest.fixture
def stub(tmp_path, monkeypatch):
    table = tmp_path / "canned.json"
    table.write_text(json.dumps(CANNED))
    script = tmp_path / "fake_run_stage.sh"
    script.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -e
        STAGE="$1"; cd "$STAGE"
        NAME="$(basename "$STAGE")"
        python3 - "$NAME" {table} <<'PY'
        import json, sys
        name, table = sys.argv[1], sys.argv[2]
        canned = json.load(open(table))
        open("output.md", "w").write(canned.get(name, ""))
        json.dump({{"is_error": False, "result": canned.get(name, ""), "total_cost_usd": 0.01,
                   "duration_ms": 1200, "usage": {{"input_tokens": 3000, "output_tokens": 120,
                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
                   "modelUsage": {{"stub-model": {{}}}}}}, open("usage.json", "w"))
        PY
        echo "stub $NAME"
        """))
    script.chmod(0o755)
    monkeypatch.setattr(classify, "RUN_STAGE", script)
    monkeypatch.setattr(claims, "RUN_STAGE", script)
    return table


def prepare_run(state_dir):
    rd = common.run_dir(DAY)
    (rd / "00-inputs").mkdir()
    (rd / "00-inputs/log.txt").write_text("\n".join([BAR1, A1, BAR2, A2]) + "\n")
    (rd / "10-transcribe").mkdir()
    (rd / "10-transcribe/wake-1247.txt").write_text(f"{A1}\nbar: {BAR1}\n")
    (rd / "10-transcribe/wake-1300.txt").write_text(f"{A1}\nbar: {BAR1}\n{A2}\nbar: {BAR2}\n")
    (rd / "10-transcribe/window.txt").write_text(f"{A1}\n{A2}\n14:59 CT  EVENT SUPERLATIVE MAX-VOL  sig=alert  vol=60323\n")
    (rd / "live-lane").mkdir()
    wakes = [
        {"lines": [A1], "bar": BAR1, "delivered_ct": "2026-08-27T12:48:22-05:00",
         "reply": {"text": "First alert: a clean rejection at 7747, vol 1808. Rejections at resistance in a range are fade context; we are in a range. Nothing to do here.",
                   "pushes": ["[ALERT] 7747 rejected"], "tool_uses": [], "usage": {"output_tokens": 1}}},
        {"lines": [A2], "bar": BAR2, "delivered_ct": "2026-08-27T13:01:25-05:00",
         "reply": {"text": "Second alert, same geometry: a failed breakdown at 7745 on vol 2251.",
                   "pushes": [], "tool_uses": [], "usage": {"output_tokens": 1}}},
    ]
    (rd / "live-lane/wakes.jsonl").write_text("".join(json.dumps(w) + "\n" for w in wakes))
    common.write_json(rd / "live-lane/session.json", {"sessions": [{"derived": {
        "wakes": [{"minute": "12:47", "lines": [A1], "bar": BAR1}, {"minute": "13:00", "lines": [A2], "bar": BAR2}],
        "undelivered": ["09:53 CT  EVENT CLIMAX BUY  sig=alert  delta=+700"], "ambiguous": []}}]})
    common.update_run_json(DAY, "inputs", {"events": {"alerts": 29, "rth_alerts": 16, "rth_notes": 36},
                                           "live_log": {"present": True, "start_ct": "2026-08-27T09:54:47-05:00"},
                                           "levels": {"loaded": 59}, "knobs": {}, "commits": {}})
    common.update_run_json(DAY, "live_lane", {"sessions_detail": [{"project": "p", "task_id": "t",
                                                                   "runbook_read_before_first_wake": True,
                                                                   "wake_sets_match": True, "usage_from_arm": {}}]})
    excerpts.build(DAY)
    return rd


def test_classify_assembles_only_sources_and_slice_and_checks_output(state_dir, stub):
    rd = prepare_run(state_dir)
    assert classify.main([DAY.isoformat()]) == 0
    inp = (rd / "20-classify/wake-1247/input.txt").read_text()
    assert "## SOURCES" in inp and "orb-target-1: knowledge/orb-playbook.md:35-37 @ 3b276c2 (trusted)" in inp
    assert "## EVENTS" in inp and A1 in inp and f"bar: {BAR1}" in inp
    assert A2 not in inp                       # a per-wake slice carries only what was delivered so far
    assert "emitter-two-tier" not in inp        # the runbook never enters the model's input
    assert (rd / "20-classify/wake-1247/prompt.md").read_text() == classify.PROMPT.read_text()
    run = common.read_json(rd / "run.json")["classify"]
    assert run["calls"] == 3 and run["all_ok"] and run["labels"] == 6
    assert run["unsourced"] == 4 and run["cost_usd_list"] == 0.03   # 3 UNSOURCED + 1 NO-RULE-IN-CANON
    assert json.loads((rd / "20-classify/window/check.json").read_text())["ok"]


def test_classify_refuses_when_the_checker_fails(state_dir, stub):
    rd = prepare_run(state_dir)
    canned = json.loads(stub.read_text())
    canned["wake-1247"] = 'LABEL 12:47 level_reject regime=rotation cite=orb-gex-sign because="rotation means fade the edge"\n'
    stub.write_text(json.dumps(canned))
    with pytest.raises(common.LaneError, match="folder is not bounding the model"):
        classify.main([DAY.isoformat()])
    run = common.read_json(rd / "run.json")["classify"]
    assert run["all_ok"] is False and run["slices"][0]["failures"] == 1


def test_classify_refuses_a_touched_context_folder(state_dir, stub):
    rd = prepare_run(state_dir)
    (rd / "20-classify/context/extra.md").write_text("a rule\n")
    with pytest.raises(common.LaneError, match="not what excerpts.py generated"):
        classify.main([DAY.isoformat()])


def test_claims_feed_replies_and_planted_fixture_and_check_quotes(state_dir, stub):
    rd = prepare_run(state_dir)
    classify.main([DAY.isoformat()])
    assert claims.main([DAY.isoformat()]) == 0
    inp = (rd / "40-compare/claims/input.txt").read_text()
    assert "## AUDIT LABELS" in inp and "### Wake 12:47" in inp and "LABEL 12:47 level_reject" in inp
    assert "## REPLIES" in inp and "a clean rejection at 7747" in inp
    assert "Push to the trader's phone: [ALERT] 7747 rejected" in inp
    live = (rd / "40-compare/claims/live.txt").read_text()
    assert "a clean rejection at 7747" in live and "[ALERT] 7747 rejected" in live
    planted_in = (rd / "40-compare/planted/input.txt").read_text()
    assert "planted test text" in planted_in and "fade/skip context per the playbook" in planted_in
    run = common.read_json(rd / "run.json")["claims"]
    assert run["calls"] == 2 and run["all_ok"]


def test_claims_refuse_a_quote_not_in_the_reply(state_dir, stub):
    prepare_run(state_dir)
    classify.main([DAY.isoformat()])
    canned = json.loads(stub.read_text())
    canned["claims"] = 'CLAIM 12:47 kind=rule quote="words the analyst never wrote" cite=UNSOURCED\n'
    stub.write_text(json.dumps(canned))
    with pytest.raises(common.LaneError, match="checker failed on \\['claims'\\]"):
        claims.main([DAY.isoformat()])


def test_compare_assigns_the_classes_and_the_planted_verdict(state_dir, stub):
    rd = prepare_run(state_dir)
    classify.main([DAY.isoformat()])
    claims.main([DAY.isoformat()])
    assert compare.main([DAY.isoformat(), "--no-publish"]) == 0
    run = common.read_json(rd / "run.json")["compare"]
    # wake 12:47: live said "rejection" (level_reject) and lane said level_reject → no B on setup;
    # live said "in a range" (rotation) vs lane unstated → B on regime; one unsourced rule → A;
    # the unsourced setup claim is also A. wake 13:00: live "failed breakdown" vs lane none → B.
    assert run["classes"] == {"A": 3, "B": 2, "C": 0, "D": 0, "agree": 0}
    assert run["claims"] == 4 and run["planted_passed"] is True and run["model_ran"] is True
    cls = common.read_json(rd / "40-compare/classes.json")
    w1 = cls["wakes"][0]
    assert [b["what"] for b in w1["B"]] == ["regime"] and w1["B"][0]["live"] == "rotation"
    assert [c["kind"] for c in w1["A"]] == ["setup", "rule"]
    assert w1["unextracted"] == []            # every rule-shaped sentence was quoted from
    w2 = cls["wakes"][1]
    assert w2["B"][0] == {**w2["B"][0], "what": "setup", "lane": "none", "live": "failed_breakdown"}
    assert cls["planted"]["passed"] and cls["planted"]["class_a"] == 3
    md = (rd / "page.md").read_text()
    assert "A (unsourced rule): 3, B (label or regime differs): 2" in md
    assert "Planted test: PASSED" in md
    assert "## Class A — rules in the live replies that no source supports (the alarm)" in md
    assert "“rejections at resistance in a range are fade context”" in md
    assert "The lane's label (from the alert lines delivered up to this wake only): level_reject" in md
    assert "20-classify/prompt.md (commit" in md and "manifest.yaml (commit" in md


def test_compare_refuses_when_the_planted_test_fails(state_dir, stub):
    rd = prepare_run(state_dir)
    classify.main([DAY.isoformat()])
    canned = json.loads(stub.read_text())
    canned["planted"] = 'CLAIM 09:31 kind=setup quote="It met every mechanical failed-breakdown criterion" cite=UNSOURCED\n'
    stub.write_text(json.dumps(canned))
    claims.main([DAY.isoformat()])
    with pytest.raises(common.LaneError, match="planted test failed"):
        compare.main([DAY.isoformat(), "--no-publish"])
    v = common.read_json(rd / "40-compare/classes.json")["planted"]
    assert not v["passed"] and len(v["reasons"]) == 3


def test_unextracted_flags_a_tripwire_sentence_no_claim_quotes(state_dir):
    r = compare.assign_classes(
        "12:47", "A rejection at 7747. Positive GEX is hostile to continuation here. Vol 1808.",
        [{"type": "LABEL", "t": "12:47", "setup": "none", "regime": "unstated", "cite": "UNSOURCED"}],
        [{"type": "CLAIM", "t": "12:47", "kind": "setup", "quote": "A rejection at 7747", "cite": "UNSOURCED"}],
        {"not_found": []}, ["hostile", "continuation"])
    assert r["unextracted"] == ["Positive GEX is hostile to continuation here."]
    assert r["B"][0]["live"] == "level_reject" and r["B"][0]["lane"] == "none"
    assert [c["quote"] for c in r["A"]] == ["A rejection at 7747"]


def test_an_unsourced_pattern_word_outside_the_vocabulary_is_not_an_alarm():
    r = compare.assign_classes(
        "10:56", "A 99.5th-percentile buy climax. Not calling it.",
        [{"type": "LABEL", "t": "10:56", "setup": "none", "regime": "unstated", "cite": "UNSOURCED"}],
        [{"type": "CLAIM", "t": "10:56", "kind": "setup", "quote": "A 99.5th-percentile buy climax", "cite": "UNSOURCED"},
         {"type": "CLAIM", "t": "10:56", "kind": "implication", "quote": "Not calling it", "cite": "UNSOURCED"}],
        {"not_found": []}, [])
    assert [c["quote"] for c in r["A"]] == ["Not calling it"]
    assert r["B"] == [{**r["B"][0], "what": "setup", "lane": "none", "live": "unmapped"}]


def test_setup_and_regime_mapping_are_derived_from_the_recognizer_names():
    assert compare.setup_of("a clean failed-breakdown of 7680") == "failed_breakdown"
    assert compare.setup_of("the 7738 reclaim") == "level_reclaim"
    assert compare.setup_of("rejected at 7747") == "level_reject"
    assert compare.setup_of("return to the LVN") == "return_to_lvn"
    assert compare.setup_of("a range trap") == "range_trap"
    assert compare.setup_of("just chop") is None
    assert compare.regime_of("we are trending") == "trending"
    assert compare.regime_of("choppy, rotational tape") == "rotation"
    assert compare.regime_of("nothing here") is None
