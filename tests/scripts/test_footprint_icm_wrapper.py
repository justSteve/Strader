"""footprint-icm-wrapper.sh — the daily audit-lane trigger's contract. [st-l3z8]

Every case runs the real wrapper with a stub standing in for run_day.sh, a tmp
corpus root (so emit_alert writes a tmp _health.jsonl, never the real one), a
tmp heartbeat and a tmp log dir. What is protected:

  - a clean run leaves an `ok` heartbeat naming the day and no alert;
  - a refusal (rc=2) leaves a `failed` heartbeat and one alert line in the
    health log carrying the day and the return code;
  - a hung run is cut at ICM_TIMEOUT_SECS and alerted as rc=124;
  - the heartbeat is written `running` before the run starts, so a mid-run
    death (the trial's recorded hazard) is visible as not-ok rather than as a
    stale `ok` from yesterday;
  - a missing entry point is alerted and never silently succeeds.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "cron" / "footprint-icm-wrapper.sh"
VENV_PY = REPO / ".venv" / "bin" / "python"
DAY = "2026-08-27"

pytestmark = pytest.mark.skipif(not VENV_PY.exists(), reason="needs the repo venv")


class Harness:
    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.corpus = tmp_path / "corpus"
        self.corpus.mkdir()
        self.health = self.corpus / "_health.jsonl"
        self.hb = tmp_path / "state" / "strader-footprint-icm.json"
        self.logdir = tmp_path / "logs"
        self.run_day = tmp_path / "run_day.sh"

    def stub(self, body: str) -> None:
        self.run_day.write_text("#!/usr/bin/env bash\n" + body + "\n")
        self.run_day.chmod(0o755)

    def run(self, timeout_secs: int = 30, **extra) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update({
            "STRADER_REPO": str(REPO),
            "STRADER_PY": str(VENV_PY),
            "STRADER_CORPUS_ROOT": str(self.corpus),
            "ICM_RUN_DAY": str(self.run_day),
            "ICM_DAY": DAY,
            "ICM_HEARTBEAT": str(self.hb),
            "ICM_LOG_DIR": str(self.logdir),
            "ICM_TIMEOUT_SECS": str(timeout_secs),
        })
        env.update(extra)
        return subprocess.run(["bash", str(WRAPPER)], env=env, capture_output=True, text=True,
                              timeout=120)

    def heartbeat(self) -> dict:
        return json.loads(self.hb.read_text())

    def alerts(self) -> list[dict]:
        if not self.health.exists():
            return []
        return [json.loads(l) for l in self.health.read_text().splitlines() if l.strip()]

    def log(self) -> str:
        return (self.logdir / f"{DAY}.log").read_text()


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


def test_a_clean_run_leaves_an_ok_heartbeat_and_no_alert(h):
    h.stub('echo "stub run_day $1"; exit 0')
    r = h.run()
    assert r.returncode == 0
    hb = h.heartbeat()
    assert hb["status"] == "ok" and hb["day"] == DAY and hb["rc"] == 0
    assert f"desk-footprint-icm-{DAY}.html" in hb["detail"]
    assert h.alerts() == []
    assert f"stub run_day {DAY}" in h.log()
    assert "(rc=0)" in h.log()


def test_a_refusal_is_alerted_with_the_day_and_return_code(h):
    h.stub('echo "[REFUSED] inputs: no live record" >&2; exit 2')
    r = h.run()
    assert r.returncode == 2
    hb = h.heartbeat()
    assert hb["status"] == "failed" and hb["rc"] == 2 and "refused" in hb["detail"]
    [alert] = h.alerts()
    assert alert["kind"] == "footprint-icm" and alert["level"] == "alert"
    assert alert["day"] == DAY and alert["returncode"] == 2
    assert "rc=2" in alert["message"]


def test_a_hung_run_is_cut_at_the_timeout_and_alerted_as_124(h):
    h.stub("sleep 30")
    r = h.run(timeout_secs=2)
    assert r.returncode == 124
    hb = h.heartbeat()
    assert hb["status"] == "failed" and hb["rc"] == 124 and "timed out after 2s" in hb["detail"]
    [alert] = h.alerts()
    assert alert["returncode"] == 124 and "hung" in alert["message"]


def test_the_heartbeat_says_running_before_the_run_and_a_death_leaves_it_so(h):
    # the stub reads the heartbeat mid-run and then dies hard
    h.stub(f'cp "{h.hb}" "{h.tmp}/mid-run.json"; kill -9 $$')
    r = h.run()
    assert r.returncode != 0
    mid = json.loads((h.tmp / "mid-run.json").read_text())
    assert mid["status"] == "running" and mid["day"] == DAY
    # the wrapper survives the child's death and records the failure
    assert h.heartbeat()["status"] == "failed"
    assert len(h.alerts()) == 1


def test_a_missing_entry_point_is_alerted_never_a_silent_success(h):
    r = h.run(ICM_RUN_DAY=str(h.tmp / "nope.sh"))
    assert r.returncode == 1
    hb = h.heartbeat()
    assert hb["status"] == "failed" and "run_day.sh missing" in hb["detail"]
    [alert] = h.alerts()
    assert "entry point missing" in alert["message"]


def test_the_catalogued_cron_line_points_at_this_wrapper():
    """COO/SCHEDULE.md is the only place the trigger is declared (finding ops-cost-2)."""
    catalog = Path("/root/projects/COO/SCHEDULE.md")
    if not catalog.exists():
        pytest.skip("COO catalog not on this box")
    text = catalog.read_text()
    assert '"id": "strader-footprint-icm"' in text
    assert f'"command": "/usr/bin/bash {WRAPPER}"' in text
    assert '"schedule": "40 15 * * 1-5"' in text
