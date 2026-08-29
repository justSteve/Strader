"""The excerpt builder and every one of its refusals. [st-h0xx]

The real source list is built for real (it reads the repo's own history), so
a manifest row whose pin has gone stale turns this red the day the canon
moves — which is the point.
"""
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

import common
import excerpts

DAY = date(2026, 8, 27)


def manifest_with(tmp_path, rows, **over):
    doc = {"version": 1, "allowed_paths": ["knowledge/", "market/orderflow/recognizer.py"],
           "refused_files": ["knowledge/counter-dictum-program.md",
                             "knowledge/carmine-rosato-investitrade-lvn-method.md"],
           "refused_statuses": ["under-review", "tabled", "withdrawn"], "rows": rows}
    doc.update(over)
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(doc))
    return p


ORB = {"id": "orb-target-1", "path": "knowledge/orb-playbook.md", "commit": "3b276c2",
       "lines": [[35, 37]], "status": "trusted", "quote": "skip the trade or downgrade the expectation"}


def test_the_real_manifest_builds_and_its_pins_hold(state_dir):
    rec = excerpts.build(DAY)
    ctx = common.run_dir(DAY) / "20-classify/context"
    idx = json.loads((ctx / "index.json").read_text())
    assert rec["rows"] == 8 == len(idx["rows"])
    assert rec["statuses"] == {"trusted": 6, "exploratory": 1, "code": 1}
    orb = (ctx / "orb-target-1.md").read_text()
    assert orb.startswith("orb-target-1: knowledge/orb-playbook.md:35-37 @ 3b276c2 (trusted)")
    assert "skip the trade or downgrade the expectation" in orb
    # the trapped-seller sentence crosses a line break with ** inside it and
    # still counts as verbatim
    tsf = (ctx / "tsf-ceiling.md").read_text()
    assert common.contains_verbatim(tsf, "trades tell us where aggression happened, not who is "
                                         "still holding or where anyone's stop sits")
    trip = json.loads((common.run_dir(DAY) / "40-compare/tripwire.json").read_text())
    assert {"fade/skip", "playbook", "expectancy", "validity", "downgrade",
            "failed_breakdown", "level_reclaim"} <= set(trip["words"])
    assert "the" not in trip["words"] and "here" not in trip["words"]
    assert excerpts.verify(common.run_dir(DAY)) == []


def test_a_hand_added_or_edited_file_fails_verify(state_dir):
    excerpts.build(DAY)
    ctx = common.run_dir(DAY) / "20-classify/context"
    (ctx / "my-notes.md").write_text("a rule I remember\n")
    assert excerpts.verify(common.run_dir(DAY)) == ["my-notes.md"]
    (ctx / "my-notes.md").unlink()
    p = ctx / "orb-gex-sign.md"
    p.write_text(p.read_text() + "and rotation means fade\n")
    assert excerpts.verify(common.run_dir(DAY)) == ["EDITED orb-gex-sign.md"]


def test_refuses_a_path_outside_knowledge(state_dir, tmp_path):
    m = manifest_with(tmp_path, [{**ORB, "id": "x", "path": "docs/playbooks/emitter-two-tier.md",
                                  "commit": "HEAD", "lines": [[76, 80]]}])
    with pytest.raises(common.LaneError, match="outside allowed_paths"):
        excerpts.build(DAY, m)


def test_refuses_the_named_withdrawn_class_files(state_dir, tmp_path):
    m = manifest_with(tmp_path, [{**ORB, "id": "x", "path": "knowledge/counter-dictum-program.md",
                                  "commit": "HEAD", "lines": [[1, 3]]}])
    with pytest.raises(common.LaneError, match="refused file"):
        excerpts.build(DAY, m)


@pytest.mark.parametrize("status", ["under-review", "tabled", "withdrawn"])
def test_refuses_the_refused_statuses(state_dir, tmp_path, status):
    m = manifest_with(tmp_path, [{**ORB, "status": status}])
    with pytest.raises(common.LaneError, match="is refused"):
        excerpts.build(DAY, m)


def test_refuses_an_unknown_status_and_a_code_row_past_the_docstring(state_dir, tmp_path):
    with pytest.raises(common.LaneError, match="unknown status"):
        excerpts.build(DAY, manifest_with(tmp_path, [{**ORB, "status": "canon"}]))
    with pytest.raises(common.LaneError, match="lines 1-38 only"):
        excerpts.build(DAY, manifest_with(tmp_path, [{
            "id": "r", "path": "market/orderflow/recognizer.py", "commit": "57eec8c",
            "lines": [[1, 60]], "status": "code", "quote": "Four-beat"}]))
    with pytest.raises(common.LaneError, match="must carry status 'code'"):
        excerpts.build(DAY, manifest_with(tmp_path, [{
            "id": "r", "path": "market/orderflow/recognizer.py", "commit": "57eec8c",
            "lines": [[1, 10]], "status": "trusted", "quote": "Four-beat"}]))


def test_refuses_when_canon_moved_since_the_pin(state_dir, tmp_path, monkeypatch):
    real = excerpts.git_lines

    def moved(ref, path):
        lines = real(ref, path)
        if ref == "HEAD":
            lines = list(lines)
            lines[35] = "hit — hold through the wall, the target always gets hit."
        return lines
    monkeypatch.setattr(excerpts, "git_lines", moved)
    with pytest.raises(common.LaneError, match="canon moved, re-pin"):
        excerpts.build(DAY, manifest_with(tmp_path, [ORB]))


def test_refuses_a_row_whose_quote_is_not_in_its_own_lines(state_dir, tmp_path):
    with pytest.raises(common.LaneError, match="quote is not in its own lines"):
        excerpts.build(DAY, manifest_with(tmp_path, [{**ORB, "quote": "fade/skip context"}]))


def test_refuses_duplicate_ids_and_bad_ranges(state_dir, tmp_path):
    with pytest.raises(common.LaneError, match="duplicate row ids"):
        excerpts.build(DAY, manifest_with(tmp_path, [ORB, ORB]))
    with pytest.raises(common.LaneError, match="outside the file"):
        excerpts.build(DAY, manifest_with(tmp_path, [{**ORB, "lines": [[35, 9999]]}]))


def test_context_is_regenerated_clean_each_build(state_dir):
    excerpts.build(DAY)
    ctx = common.run_dir(DAY) / "20-classify/context"
    (ctx / "stale.md").write_text("x")
    excerpts.build(DAY)
    assert not (ctx / "stale.md").exists()
