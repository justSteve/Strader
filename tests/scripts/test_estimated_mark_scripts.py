"""The calibrate and validate scripts, end to end on a synthetic corpus. [st-9hhc]

Pinned: two runs with unchanged code are byte-identical (calibration JSON,
rows JSONL, write-up); the write-up states the coverage bound before any
premium-shaped number; holdout days are labelled; a day with prints before
the window is counted in the bound and not used outside it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from strader.marks.estimated import Calibration
from tests.helpers.estimated_mark_corpus import write_corpus

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "scripts" / "measurement" / "estimated_mark_calibrate.py"
VAL = ROOT / "scripts" / "measurement" / "estimated_mark_validate.py"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    c = tmp_path_factory.mktemp("corpus")
    # Drifts in ES points per minute: -0.2 is a 24-point slide over the two
    # hours, +0.35 a 42-point rally that runs the calls deep and kills the puts.
    write_corpus(c, {
        "2025-11-03": {"drift_per_min": -0.2},
        "2025-11-04": {"drift_per_min": +0.35, "gz": True},
        "2025-11-05": {"drift_per_min": -0.05, "opra_from": "12:45"},  # prints before the window
        "2026-02-10": {"drift_per_min": +0.15},                         # the holdout day
    })
    (c / "not-a-day").mkdir()
    (c / "2026-02-11").mkdir()          # a day directory with no files: ignored
    return c


def _run(script: Path, *args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run([sys.executable, str(script), *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.fixture(scope="module")
def calibrated(corpus, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    cal_a = out / "cal-a.json"
    cal_b = out / "cal-b.json"
    common = ("--corpus", str(corpus), "--days-through", "2025-12-31",
              "--min-rows", "40", "--min-legs", "2", "--workers", "2")
    _run(CAL, "--out", str(cal_a), *common)
    _run(CAL, "--out", str(cal_b), *common)
    return out, cal_a, cal_b


def test_calibration_is_byte_identical_across_runs_and_records_its_sources(calibrated):
    _, a, b = calibrated
    assert a.read_bytes() == b.read_bytes()
    cal = Calibration.load(a)
    assert cal.window_ct == ("13:00", "15:00")
    assert cal.days == ("2025-11-03", "2025-11-04", "2025-11-05")      # the 2026 day was held out
    assert cal.fits, "no bin was fitted"
    for f in cal.fits.values():
        assert 0.0 <= f.delta_pts_per_es <= 1.5
        assert f.n_legs >= 2 and f.n_rows >= 40
    s = cal.coverage["summary"]
    assert s["n_days"] == 3
    assert s["days_with_prints_before_window"] == 1
    assert s["days_before_window_list"] == ["2025-11-05"]
    assert s["earliest_first_minute_ct"] == "12:45"
    assert cal.source["script"].endswith("estimated_mark_calibrate.py")
    assert cal.source["days_through"] == "2025-12-31"
    assert "leg_skips" in cal.source and "thin_bins" in cal.source
    text = a.read_text()
    assert "generated" not in text.lower() and "T00:" not in text      # no clock in the file


def test_validation_is_byte_identical_labels_holdout_and_leads_with_coverage(corpus, calibrated):
    out, cal_a, _ = calibrated
    run_a, run_b = out / "run-a", out / "run-b"
    run_a.mkdir()
    run_b.mkdir()
    rows_a, rows_b = run_a / "rows.jsonl", run_b / "rows.jsonl"
    doc_a, doc_b = run_a / "doc.md", run_b / "doc.md"
    # Relative output paths from two working directories: the write-up names
    # its inputs, so the names must match for the bytes to.
    common = ("--corpus", str(corpus), "--calibration", str(cal_a), "--as-of", "2026-09-03",
              "--workers", "2", "--rows", "rows.jsonl", "--doc", "doc.md")
    stdout = _run(VAL, *common, cwd=run_a)
    _run(VAL, *common, cwd=run_b)
    assert rows_a.read_bytes() == rows_b.read_bytes()
    assert doc_a.read_bytes() == doc_b.read_bytes()
    assert "scored" in stdout

    rows = [json.loads(l) for l in rows_a.read_text().splitlines()]
    assert rows == sorted(rows, key=lambda r: r["leg_id"])
    scored = [r for r in rows if "skip" not in r]
    assert scored, "nothing was scored"
    days = {r["day"] for r in scored}
    assert "2026-02-10" in days
    assert all(r["in_sample"] is False for r in scored if r["day"] == "2026-02-10")
    assert all(r["in_sample"] is True for r in scored if r["day"] < "2026")
    for r in scored:
        for k in ("close_resid_pts", "mfe_resid_pts", "mae_resid_pts", "stop_abs30_print",
                  "stop_abs30_proxy_close", "stop_abs30_proxy_adverse", "stop_pct10_print",
                  "target25_print", "target25_proxy", "right_direction", "bin_lo"):
            assert k in r, k
        assert r["n_minutes"] >= 5
        assert r["last_minute"] == "14:59"
    # Every minute the proxy marked sits inside the window: the entry is at or after 13:00.
    assert all(r["entry_ct"] >= "13:00" for r in rows)
    # Legs in a bin the calibration never fitted are skipped as such, never guessed.
    skipped = {r["skip"] for r in rows if "skip" in r}
    assert skipped <= {"uncalibrated", "thin-overlap", "coverage"}

    doc = doc_a.read_text()
    assert doc.startswith("# Estimated Mark Path")
    cov_at = doc.index("## 0. The coverage bound")
    first_number_section = doc.index("## 3. Calibration")
    assert cov_at < doc.index("## 1. What was measured") < doc.index("## 2. The model") < first_number_section
    assert "days with any print before 13:00 CT | **1 of 4**" in doc
    assert "2025-11-05" in doc
    assert "## 4. Stop-fire timing" in doc and "The 82% question" in doc
    assert "## 5. Close-mark residual" in doc
    assert doc.index("## 4. Stop-fire timing") < doc.index("## 5. Close-mark residual")
    assert "exit_reason=time" in doc
    assert "**measured**" in doc.lower() and "**reasoned**" in doc.lower()
    assert "13:00–15:00 CT only" in doc
    assert "| holdout | " in doc


def test_validate_refuses_an_empty_corpus(tmp_path, calibrated):
    _, cal_a, _ = calibrated
    r = subprocess.run([sys.executable, str(VAL), "--corpus", str(tmp_path), "--calibration", str(cal_a),
                        "--rows", str(tmp_path / "r.jsonl"), "--doc", str(tmp_path / "d.md")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2 and "no corpus days" in r.stderr
