"""Stage 00 against the archive. [st-h0xx]

These read real days from ``data/corpus`` and the live logs under
``/var/moo/logs`` and skip where either is absent, the same discipline as
``tests/scripts/test_replay_emissions.py``. They write only under a temporary
run root.
"""
import json
from datetime import date
from pathlib import Path

import pytest

import common
import inputs
from market.orderflow.replay import has_es_day

DAY = date(2026, 8, 27)
corpus = pytest.mark.skipif(not has_es_day(DAY), reason=f"{DAY} not in data/corpus")
live_log = pytest.mark.skipif(not common.live_log_path(DAY).exists(),
                              reason="no live log for 08-27 on this box")


@corpus
@live_log
def test_inputs_reproduce_the_live_day_and_record_provenance(state_dir):
    rc = inputs.main([DAY.isoformat(), "--no-log-body"])
    assert rc == 0
    rd = common.run_dir(DAY)
    run = common.read_json(rd / "run.json")["inputs"]
    assert run["events"]["total"] == 113 and run["events"]["alerts"] == 29
    assert run["events"]["rth_total"] == 52 and run["events"]["rth_alerts"] == 16
    assert run["live_log"]["event_lines_equal_replay"] is True
    assert run["live_log"]["levels_loaded"] == 59 == run["levels"]["loaded"]
    assert run["live_log"]["start_ct"].startswith("2026-08-27T09:54:47")
    assert run["levels"]["source"] == "letter" and len(run["levels"]["sha256"]) == 64
    assert run["knobs"]["climax_min_atoms"] == "60"
    assert set(run["commits"]) >= {"market/orderflow/tape_events.py", "config/tape_events.yaml"}
    recs = [json.loads(l) for l in (rd / "00-inputs/events.jsonl").read_text().splitlines()]
    assert len(recs) == 113 and recs[0]["kind"] == "PLAN-LEVEL"
    rth = [json.loads(l) for l in (rd / "00-inputs/events.rth.jsonl").read_text().splitlines()]
    assert all("08:30" <= r["line"][:5] <= "15:00" for r in rth)
    assert json.loads((rd / "00-inputs/levels.json").read_text())["parsed_at"]


@corpus
def test_inputs_refuse_when_thresholds_drift(state_dir, tmp_path, monkeypatch):
    """A live log whose '# knobs:' line differs from the yaml as loaded is a
    refusal: a replay under other thresholds is a different instrument."""
    fake = tmp_path / f"{DAY}.log"
    real = common.live_log_path(DAY)
    if not real.exists():
        pytest.skip("no live log for 08-27 on this box")
    text = real.read_text()
    text = text.replace("climax_min_atoms=60", "climax_min_atoms=61", 1)
    fake.write_text(text)
    monkeypatch.setattr(inputs, "live_log_path", lambda d: fake)
    with pytest.raises(common.LaneError, match="thresholds differ"):
        inputs.main([DAY.isoformat(), "--no-log-body"])
    assert common.read_json(common.run_dir(DAY) / "run.json")["inputs"]["refused"] == "knobs differ"


@corpus
def test_inputs_refuse_when_the_live_events_differ(state_dir, tmp_path, monkeypatch):
    fake = tmp_path / f"{DAY}.log"
    real = common.live_log_path(DAY)
    if not real.exists():
        pytest.skip("no live log for 08-27 on this box")
    lines = real.read_text().splitlines()
    # drop the first EVENT line
    idx = next(i for i, ln in enumerate(lines) if common.EVENT_RE.match(ln))
    del lines[idx]
    fake.write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(inputs, "live_log_path", lambda d: fake)
    with pytest.raises(common.LaneError, match="EVENT lines differ"):
        inputs.main([DAY.isoformat(), "--no-log-body"])


def test_inputs_refuse_a_day_with_no_corpus(state_dir):
    with pytest.raises(common.LaneError, match="no ES corpus"):
        inputs.main(["2019-01-01", "--no-log-body"])
