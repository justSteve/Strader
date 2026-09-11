"""The replay lane end to end on a synthetic corpus: rows on the days a rule
fires, every call accounted for, byte-identical twice, the write-up split
by mark path. [st-uc23]"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from strader.blotter import replay as R
from strader.blotter.report import aggregate, grid_table, render_markdown
from strader.blotter.rules import load_rules
from strader.marks.estimated import BinFit, Calibration
from tests.helpers.estimated_mark_corpus import write_corpus

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "measurement" / "blotter_replay.py"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    c = tmp_path_factory.mktemp("corpus")
    write_corpus(c, {
        "2025-11-03": {"drift_per_min": +0.35, "side_bias": 0.7},     # fires, printed
        "2025-11-04": {"drift_per_min": -0.30, "side_bias": 0.3},     # no fire
        "2026-02-10": {"drift_per_min": +0.35, "side_bias": 0.7, "opra_from": "15:00"},  # fires, estimated
        "2026-02-11": {"drift_per_min": +0.35, "side_bias": 0.7, "opra_from": "15:00"},  # fires, unpriceable
    })
    d = c / "2026-02-10"
    cw = [{"strike": float(k), "side": side, "bid": 9.9, "ask": 10.0, "mark": 9.95}
          for k in range(6300, 6600, 5) for side in ("CALL", "PUT")]
    (d / "schwab.jsonl").write_text(json.dumps({
        "ts_pull_utc": "2026-02-10T20:45:08Z", "stage": "close-watch",
        "data": {"spot_spx": 6431.7, "spot_es": 6451.7, "chain_window": cw}}) + "\n")
    (c / "2026-02-12").mkdir()      # a day directory with no files: not a corpus day
    return c


@pytest.fixture(scope="module")
def parsed(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("parsed")
    # A resistance far above: no lid within 10, so launch-into-no-lid fires too.
    (p / "2025-11-03.json").write_text(json.dumps({"levels": [{"price": 6900.0, "kind": "resistance"}]}))
    return p


@pytest.fixture(scope="module")
def cal_path(tmp_path_factory) -> Path:
    fits = {(r, lo): BinFit(r, lo, 0.7, 0.5, 1000, 1000, 50, 0.5, 0.0)
            for r in ("C", "P") for lo in range(-20, 20, 5)}
    p = tmp_path_factory.mktemp("cal") / "cal.json"
    Calibration(fits=fits, days=("2025-01-02",)).dump(p)
    return p


def test_corpus_days_in(corpus):
    assert R.corpus_days_in(corpus, "2025-01-01", "2026-12-31") == ["2025-11-03", "2025-11-04", "2026-02-10", "2026-02-11"]
    assert R.corpus_days_in(corpus, "2026-02-11", "2026-02-11") == ["2026-02-11"]
    assert R.corpus_days_in(corpus / "nope", "2025-01-01", "2026-12-31") == []


def test_replay_day_rows_and_accounting(corpus, parsed, cal_path):
    rules = load_rules()
    cal = Calibration.load(cal_path)
    up = R.replay_day("2025-11-03", rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    assert up.skip is None and len(up.rows) == 2 and not up.unpriced
    ids = [r["id"] for r in up.rows]
    assert ids == ["2025-11-03-footprint-up-1445-1", "2025-11-03-launch-into-no-lid-1445-1"]
    row = up.rows[0]
    assert row["mark_path"] == "prints" and row["estimated"] is False and row["grid"]
    assert row["registered"] == "ac02296" and row["excerpts"] == ["footprint-up-1445"]
    assert row["replay"] == "2025-11-03 14:15 to 15:00" and row["events"] == []
    assert "out" not in row["state"] and row["state"]["fp"]["pos"] >= 0.8
    assert row["pnl_usd"] == round(row["pnl_pts"] * 100, 2)
    assert row["lane"] == "replay" and row["lots"] == 1 and row["right"] == "C"

    down = R.replay_day("2025-11-04", rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    assert down.rows == [] and [f["call"] for f in down.fires] == [None, None]

    est = R.replay_day("2026-02-10", rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    assert len(est.rows) == 2 and all(r["estimated"] and r["exit_reason"] == "time" and r["grid"] is None for r in est.rows)
    assert est.rows[0]["estimated_exit"]["would_exit_reason_extreme"] in ("stop", "target", "time")

    none = R.replay_day("2026-02-11", rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    assert none.rows == [] and len(none.unpriced) == 2
    assert {u["reason"] for u in none.unpriced} == {"no-entry-source"}
    assert all(f.get("priced") is False for f in none.fires)

    gone = R.replay_day("2026-02-12", rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    assert gone.skip == "no-es-file"


def test_replay_range_serial_and_pool_agree(corpus, parsed, cal_path):
    days = R.corpus_days_in(corpus, "2025-01-01", "2026-12-31")
    a = R.replay_range(days, corpus=corpus, parsed=parsed, cal_path=cal_path, events=False, workers=1)
    b = R.replay_range(days, corpus=corpus, parsed=parsed, cal_path=cal_path, events=False, workers=2)
    assert [json.dumps(x.to_dict(), sort_keys=True) for x in a] == [json.dumps(x.to_dict(), sort_keys=True) for x in b]
    assert [len(x.rows) for x in a] == [2, 0, 2, 0]


def test_write_day_rows_only_for_days_with_rows(corpus, parsed, cal_path, tmp_path):
    rules = load_rules()
    cal = Calibration.load(cal_path)
    rep = R.replay_day("2025-11-04", rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    assert R.write_day_rows(tmp_path, rep) is None
    rep = R.replay_day("2025-11-03", rules, corpus=corpus, parsed=parsed, cal=cal, events=False)
    p = R.write_day_rows(tmp_path, rep)
    assert p == tmp_path / "replay-2025-11-03.jsonl"
    lines = p.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["id"].endswith("-1")


def test_report_splits_by_mark_path(corpus, parsed, cal_path):
    days = R.corpus_days_in(corpus, "2025-01-01", "2026-12-31")
    reps = R.replay_range(days, corpus=corpus, parsed=parsed, cal_path=cal_path, events=False)
    rows = [r for rep in reps for r in rep.rows]
    agg = aggregate(rows)
    assert set(agg) == {"footprint-up-1445", "launch-into-no-lid-1445"}
    assert set(agg["footprint-up-1445"]) == {"prints", "estimated"}
    assert agg["footprint-up-1445"]["prints"]["all"]["n"] == 1 and agg["footprint-up-1445"]["estimated"]["all"]["n"] == 1
    assert "2025" in agg["footprint-up-1445"]["prints"] and "2026" in agg["footprint-up-1445"]["estimated"]
    assert agg["footprint-up-1445"]["estimated"]["exits"] == {"time": 1}
    g = grid_table(rows)
    assert len(g["footprint-up-1445"]) == 16 and g["footprint-up-1445"]["0.30x25"]["n"] == 1
    meta = [{"id": "footprint-up-1445", "fire_at": ["14:45"], "instrument": "itm-single-10",
             "exit": {"stop_pts": 0.3, "target_pct": 25, "time": "15:00 CT"}, "registered": "ac02296"}]
    doc = render_markdown(rows, [r.to_dict() for r in reps], as_of="2026-09-11", day_from="2025-11-03",
                          day_to="2026-02-11", rules_meta=meta, calibration="cal.json", estimated_mark_doc=None)
    assert "never pooled" in doc and "| `footprint-up-1445` | estimated |" in doc and "| `footprint-up-1445` | prints |" in doc
    assert "| no-entry-source | 2 |" in doc
    assert doc.index("## 0. What was scanned") < doc.index("## 2. Rows by rule")


def test_the_script_is_byte_identical_twice(corpus, parsed, cal_path, tmp_path):
    outs = []
    for i in (1, 2):
        out = tmp_path / f"run{i}"
        doc = out / "doc.md"
        r = subprocess.run([sys.executable, str(SCRIPT), "--from", "2025-11-01", "--to", "2026-02-28",
                            "--corpus", str(corpus), "--parsed", str(parsed), "--calibration", str(cal_path),
                            "--out-dir", str(out), "--doc", str(doc), "--as-of", "2026-09-11", "--no-events",
                            "--workers", "2"], cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "4 days, 4 rows (2 printed, 2 estimated) on 2 days, 2 unpriced calls" in r.stdout
        outs.append({p.name: p.read_bytes() for p in sorted(out.iterdir())})
    assert outs[0] == outs[1]
    names = set(outs[0])
    assert names == {"replay-2025-11-03.jsonl", "replay-2026-02-10.jsonl", "replay-run-2025-11-01-2026-02-28.json", "doc.md"}
    manifest = json.loads(outs[0]["replay-run-2025-11-01-2026-02-28.json"])
    assert manifest["n_days"] == 4 and manifest["n_rows"] == 4 and manifest["n_unpriced"] == 2
    assert [d["day"] for d in manifest["days"]] == ["2025-11-03", "2025-11-04", "2026-02-10", "2026-02-11"]
    assert {r["id"] for r in manifest["rules"]} == {"footprint-up-1445", "launch-into-no-lid-1445"}


def test_the_script_refuses_an_unknown_rule_and_an_empty_range(corpus, parsed, cal_path, tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), "--from", "2025-11-03", "--rule", "nope", "--corpus", str(corpus),
                        "--calibration", str(cal_path), "--out-dir", str(tmp_path)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "unknown rule id" in r.stderr
    r = subprocess.run([sys.executable, str(SCRIPT), "--from", "2024-01-01", "--corpus", str(corpus),
                        "--calibration", str(cal_path), "--out-dir", str(tmp_path)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1 and "no corpus days" in r.stderr


def test_events_on_a_real_day_if_the_corpus_is_here():
    day = ROOT / "data" / "corpus" / "2026-08-28"
    if not (day / "databento_glbx_es.jsonl.gz").exists() and not (day / "databento_glbx_es.jsonl").exists():
        pytest.skip("2026-08-28 is not on this box")
    ev = R._events_before("2026-08-28", "14:45", 30)
    assert ev and all(e["path"] == "tape" for e in ev)
    assert all("14:15" <= e["ts"][11:16] <= "14:45" for e in ev)
