"""Every Strader cron wrapper leaves a four-state heartbeat on every exit. [co-8b60y]

Until 2026-09-04, 14 of the 17 Strader jobs wrote no heartbeat at all, so the
checker at /tap-in saw ten jobs and a week of failures left nothing on the
surface. Each wrapper now sources scripts/cron/heartbeat-lib.sh and arms an
EXIT trap: `running` at start, `ok` on rc 0, `failed` with the rc otherwise,
the wrapper's own words in the detail.

Every case runs the real wrapper against a fake repo whose venv python is a
stub that exits with STUB_RC, with HB_STATE_DIR in tmp_path. Nothing here
touches /var/moo, the real venv, systemd (the Mancini feeder reconciliation is
disabled by STRADER_FEEDER_RESTART=0) or tmux (the gauge case runs on a
Saturday, which exits before any tmux call).
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CRON = REPO / "scripts" / "cron"

# The python stand-in. Inline snippets (`-` heredocs, `-c` one-liners) are the
# alert emitters and small helpers around the main call; they succeed so the
# heartbeat reflects the main call's rc alone. STUB_MARK, when set, copies the
# heartbeat as it stands mid-run so a test can see the `running` state.
STUB = """#!/usr/bin/env bash
case "${1:-}" in -|-c) exit 0 ;; esac
if [[ -n "${STUB_MARK:-}" ]]; then cp "$STUB_MARK" "$STUB_MARK.mid" 2>/dev/null; fi
exit "${STUB_RC:-0}"
"""


@pytest.fixture
def fake(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".venv" / "bin").mkdir(parents=True)
    py = repo / ".venv" / "bin" / "python"
    py.write_text(STUB)
    py.chmod(0o755)
    (repo / "scripts").mkdir()
    (repo / "logs").mkdir()
    for f in ("corpus_pull_schwab.py", "premarket_volume_profile.py", "postmortem_day.py",
              "gexbot_hist_backfill.py", "corpus_compact_databento.py", "mi_gauge.py"):
        (repo / "scripts" / f).write_text("")
    state = tmp_path / "state"
    logs = tmp_path / "logs"
    logs.mkdir()
    env = dict(os.environ)
    env.update({
        "STRADER_REPO": str(repo), "STRADER_VENV": str(repo / ".venv"), "STRADER_PY": str(py),
        "HB_STATE_DIR": str(state), "STRADER_LOG_DIR": str(logs),
        "STRADER_SCHWAB_LOGDIR": str(logs), "STRADER_TRACKER_LOGDIR": str(logs),
        "STRADER_HEARTBEAT_LOGDIR": str(logs), "STRADER_MANCINI_LOGDIR": str(logs),
        "STRADER_COMPACT_LOGDIR": str(logs), "STRADER_GAUGE_LOGDIR": str(logs),
        "STRADER_GEXBOT_HIST_LOG": str(logs / "gexbot-hist.log"),
        "STRADER_MANCINI_CLIP": "", "STRADER_FEEDER_RESTART": "0",
        "STRADER_GAUGE_MATCH": "no-such-process-ever-" + tmp_path.name,
        "STRADER_GAUGE_NOW": "2026-07-25T10:00",   # Saturday: exits before tmux
    })
    return state, env


def run(script, args, env, rc, **extra):
    e = dict(env, STUB_RC=str(rc), **extra)
    p = subprocess.run(["bash", str(script), *args], env=e, capture_output=True, text=True, timeout=90)
    return p.returncode


def heartbeat(state, job):
    return json.loads((state / f"{job}.json").read_text())


CASES = [
    (CRON / "schwab-stages-wrapper.sh", ["premarket"], "strader-schwab-premarket"),
    (CRON / "schwab-stages-wrapper.sh", ["close-watch"], "strader-schwab-close-watch"),
    (CRON / "level-tracker-wrapper.sh", [], "strader-level-tracker"),
    (CRON / "postmortem-wrapper.sh", ["same-day"], "strader-postmortem-close"),
    (CRON / "postmortem-wrapper.sh", ["next-morning"], "strader-postmortem-morning"),
    (CRON / "premarket-vp-wrapper.sh", [], "strader-premarket-vp"),
    (CRON / "preopen-heartbeat-wrapper.sh", [], "strader-preopen-heartbeat"),
    (CRON / "mancini-preopen-wrapper.sh", [], "strader-mancini-preopen"),
    (REPO / "scripts" / "gexbot_hist_nightly.sh", [], "strader-gexbot-hist-nightly"),
]


@pytest.mark.parametrize("script,args,job", CASES, ids=[c[2] for c in CASES])
def test_ok_then_failed(fake, script, args, job):
    state, env = fake
    assert run(script, args, env, 0) == 0
    h = heartbeat(state, job)
    assert h["status"] == "ok", h
    assert h["ts"].endswith("Z") and h["started"].endswith("Z")
    assert h["detail"] and h["detail"] != "completed", "the wrapper should say what it did"

    assert run(script, args, env, 3) == 3
    h = heartbeat(state, job)
    assert h["status"] == "failed", h
    assert "rc=3" in h["detail"], h
    assert h["rc"] == 3


def test_running_written_before_the_work(fake):
    state, env = fake
    mark = state / "strader-level-tracker.json"
    assert run(CRON / "level-tracker-wrapper.sh", [], env, 0, STUB_MARK=str(mark)) == 0
    mid = json.loads((state / "strader-level-tracker.json.mid").read_text())
    assert mid["status"] == "running"
    assert mid["detail"].startswith("started ")
    assert heartbeat(state, "strader-level-tracker")["status"] == "ok"


def test_venv_missing_is_a_failed_heartbeat(fake):
    state, env = fake
    env = dict(env, STRADER_VENV=str(state / "no-such-venv"))
    assert run(CRON / "schwab-stages-wrapper.sh", ["open"], env, 0) == 2
    h = heartbeat(state, "strader-schwab-open")
    assert h["status"] == "failed" and "rc=2" in h["detail"]


def test_gauge_tick_outside_window(fake):
    state, env = fake
    assert run(CRON / "gauge-preopen-wrapper.sh", [], env, 0) == 0
    assert heartbeat(state, "strader-gauge-preopen")["status"] == "ok"


def test_compact_nothing_raw(fake):
    # The vetting step is `python -` (the stub prints nothing) -> nothing to pack.
    state, env = fake
    assert run(CRON / "corpus-compact-wrapper.sh", [], env, 0) == 0
    h = heartbeat(state, "strader-corpus-compact")
    assert h["status"] == "ok" and "nothing raw" in h["detail"], h


def test_every_catalogued_strader_cron_writes_the_path_it_is_catalogued_under():
    """COO/SCHEDULE.md names the heartbeat path per job; each wrapper's hb_path
    argument must be that job id, or the checker reads MISSING forever."""
    catalog = Path("/root/projects/COO/SCHEDULE.md")
    # READABILITY, not existence. `Path.exists()` re-raises EACCES rather than
    # returning False, and on a CI runner /root is 0700 owned by another user —
    # so this guard raised PermissionError instead of skipping. The question the
    # test actually asks is "can I read the catalog", and that is one try. [st-v55j]
    try:
        text = catalog.read_text()
    except OSError as e:
        pytest.skip(f"COO catalog not readable here ({e.__class__.__name__})")
    # The fenced block starts at a line of its own; the prose above it also
    # says "```json```" in passing.
    block = text.split("\n```json\n", 1)[1].split("\n```", 1)[0]
    entries = json.loads(block)
    want = {e["id"]: e["heartbeat"] for e in entries
            if e.get("owner") == "Strader" and e.get("surface") == "cron"}
    assert want, "no Strader cron entries found"
    for job, path in want.items():
        assert path == f"/var/moo/state/{job}.json", (job, path)
    wrappers = " ".join(p.read_text() for p in list(CRON.glob("*.sh")) + [REPO / "scripts" / "gexbot_hist_nightly.sh"])
    for job in want:
        base = job.replace("strader-schwab-premarket", "strader-schwab-$STAGE") \
                  .replace("strader-schwab-open", "strader-schwab-$STAGE") \
                  .replace("strader-schwab-afternoon", "strader-schwab-$STAGE") \
                  .replace("strader-schwab-close-watch", "strader-schwab-$STAGE")
        if job in ("strader-postmortem-morning", "strader-postmortem-close"):
            base = job   # named in the wrapper's case table
        if job == "strader-footprint-icm":
            continue     # its own writer, adopted in the same change
        assert base in wrappers, f"{job}: no wrapper writes hb_path {base}"
