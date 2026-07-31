"""Schwab stage-boundary snapshot wiring. [st-096]

Three defects this file is the tripwire for:

1. The --date injection that killed --include-schwab: corpus_daily.run_pull
   appended --date to every pull, but corpus_pull_schwab.py takes no such flag
   — the pull died on argparse before reaching the API, which is why the
   schwab stream never returned to the manifests via the batch path.
2. The stage label: consumers filter on it, so it must land in the JSONL
   record and reject free text.
3. The cron wrapper must pass its stage argument through to the shim and
   propagate a failing rc (the alert path keys off it).

Everything runs against stubs — nothing here touches the gated live API.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

import scripts.corpus_pull_schwab as shim
from scripts import corpus_daily

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "cron" / "schwab-stages-wrapper.sh"

FAKE_RECORD = {
    "ts_pull_utc": "2026-07-31T12:00:00Z",
    "stream": "schwab",
    "data": {"spot_spx": 7450.0, "spot_es": 7492.0,
             "atm": {"atm_strike": 7450.0, "atm_straddle": 12.3}},
    "errors": [],
}


# --- shim: stage stamping ---------------------------------------------------

def _run_shim(monkeypatch, tmp_path, argv):
    out = tmp_path / "schwab.jsonl"
    manifests = []
    monkeypatch.setattr(shim, "pull_cycle", lambda symbol: dict(FAKE_RECORD))
    monkeypatch.setattr(shim, "schwab_path", lambda d=None: out)
    monkeypatch.setattr(shim, "update_manifest",
                        lambda **kw: manifests.append(kw))
    rc = shim.main(argv)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    return rc, rows, manifests


def test_stage_label_lands_in_record(monkeypatch, tmp_path):
    rc, rows, manifests = _run_shim(monkeypatch, tmp_path, ["--stage", "open"])
    assert rc == 0
    assert rows[0]["stage"] == "open"
    assert manifests[0]["stream"] == "schwab"


def test_default_stage_is_adhoc(monkeypatch, tmp_path):
    _, rows, _ = _run_shim(monkeypatch, tmp_path, [])
    assert rows[0]["stage"] == "adhoc"


def test_unknown_stage_rejected():
    with pytest.raises(SystemExit):
        shim.main(["--stage", "lunchtime"])


def test_cron_stages_are_known_to_the_shim():
    """The four labels the cron header installs must stay valid shim choices."""
    header = WRAPPER.read_text()
    for stage in ("premarket", "open", "afternoon", "close-watch"):
        assert stage in shim.STAGES
        assert f"schwab-stages-wrapper.sh {stage}" in header


# --- corpus_daily: no --date injection for snapshot scripts -----------------

def test_run_pull_pass_date_false_omits_date(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(corpus_daily.subprocess, "run", fake_run)
    day = corpus_daily._date(2026, 7, 30)
    corpus_daily.run_pull("corpus_pull_schwab.py", day,
                          ["--stage", "daily-batch"], pass_date=False)
    assert "--date" not in seen["cmd"]
    assert seen["cmd"][-2:] == ["--stage", "daily-batch"]


def test_run_pull_default_still_passes_date(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(corpus_daily.subprocess, "run", fake_run)
    day = corpus_daily._date(2026, 7, 30)
    corpus_daily.run_pull("corpus_pull_databento_es.py", day)
    assert "--date" in seen["cmd"]
    assert day.isoformat() in seen["cmd"]


# --- wrapper: stage passthrough and rc propagation --------------------------

def _stub_repo(tmp_path, exit_code=0):
    """A fake STRADER_REPO whose venv python records its argv and exits as told."""
    repo = tmp_path / "repo"
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / "scripts").mkdir()
    calls = repo / "calls.log"
    py = repo / ".venv" / "bin" / "python"
    py.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{calls}"\n'
        # The alert heredoc invokes `python -`; swallow its stdin and succeed
        # so only the pull's exit code drives the wrapper rc.
        '[[ "$1" == "-" ]] && { cat > /dev/null; exit 0; }\n'
        f"exit {exit_code}\n"
    )
    py.chmod(0o755)
    (repo / "scripts" / "corpus_pull_schwab.py").write_text("# stub target\n")
    return repo, calls


def _run_wrapper(repo, tmp_path, *args):
    env = dict(os.environ, STRADER_REPO=str(repo),
               STRADER_SCHWAB_LOGDIR=str(tmp_path / "logs"))
    return subprocess.run(["bash", str(WRAPPER), *args],
                          env=env, capture_output=True, text=True, timeout=30)


def test_wrapper_passes_stage_through(tmp_path):
    repo, calls = _stub_repo(tmp_path)
    proc = _run_wrapper(repo, tmp_path, "close-watch")
    assert proc.returncode == 0
    assert "--stage close-watch" in calls.read_text()


def test_wrapper_defaults_to_adhoc(tmp_path):
    repo, calls = _stub_repo(tmp_path)
    proc = _run_wrapper(repo, tmp_path)
    assert proc.returncode == 0
    assert "--stage adhoc" in calls.read_text()


def test_wrapper_propagates_failure_and_attempts_alert(tmp_path):
    repo, calls = _stub_repo(tmp_path, exit_code=1)
    proc = _run_wrapper(repo, tmp_path, "open")
    assert proc.returncode == 1
    logged = calls.read_text().splitlines()
    # first call: the pull; second call: the `python -` alert heredoc
    assert any("--stage open" in l for l in logged)
    assert any(l.strip() == "-" for l in logged)
