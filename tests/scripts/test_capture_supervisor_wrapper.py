"""capture-supervisor-wrapper.sh — relaunch, restraint, and the st-cm5 guard. [st-6qx4]

The contract under test: a dead capture inside the window is relaunched within
one tick; a live one is never touched; two live ones are reported and never
killed; a stale one is reported and left alone unless the operator has opted in.

Every case runs on a throwaway tmux socket with a python stub standing in for the
streamer (STRADER_CAPTURE_MATCH / _LAUNCH) and a tmp corpus root, so nothing here
can reach the moocity desk, the real corpus, or a Databento gateway. The bead
that authorised this work was explicit that a capture session was running while
it was written and must not be disturbed.
"""
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "cron" / "capture-supervisor-wrapper.sh"
VENV_PY = REPO / ".venv" / "bin" / "python"

ES = "databento_glbx_es"
MBP1 = "databento_glbx_es_mbp1"

NIGHT = "2026-08-04T02:00"        # Tuesday overnight — GLBX open, in window
SATURDAY = "2026-08-08T02:00"     # GLBX closed all day

pytestmark = pytest.mark.skipif(
    not shutil.which("tmux") or not VENV_PY.exists(),
    reason="needs tmux and the repo venv",
)


class Harness:
    def __init__(self, tmp_path):
        self.tag = uuid.uuid4().hex[:10]
        self.socket = f"strader-cap-{self.tag}"
        self.session = f"scratch-{self.tag}"
        self.tmp = tmp_path
        self.logdir = tmp_path / "logs"
        self.corpus = tmp_path / "corpus"
        self.state = self.corpus / "_capture_health.json"
        self.health = self.corpus / "_health.jsonl"
        self.stub = tmp_path / f"capture_stub_{self.tag}.py"
        self.stub.write_text("import time\nwhile True:\n    time.sleep(1)\n")
        self._procs = []

    # -- driving ---------------------------------------------------------
    def run(self, now=NIGHT, **extra):
        env = dict(os.environ)
        env.update({
            "STRADER_TMUX_SOCKET": self.socket,
            "STRADER_TMUX_SESSION": self.session,
            "STRADER_CAPTURE_WIN": "capture",
            "STRADER_CAPTURE_MATCH": str(self.stub),
            "STRADER_CAPTURE_LAUNCH": f"exec {VENV_PY} {self.stub}",
            "STRADER_CAPTURE_CORPUS_ROOT": str(self.corpus),
            "STRADER_CAPTURE_STATE": str(self.state),
            "STRADER_CAPTURE_HEALTH_LOG": str(self.health),
            "STRADER_CAPTURE_LOGDIR": str(self.logdir),
            "STRADER_CAPTURE_NOW": now,
            # The stub is launched moments before it is inspected; production's
            # 180s connect grace would report every test as "starting".
            "STRADER_CAPTURE_GRACE_SECS": "0",
        })
        env.update(extra)
        p = subprocess.run(["bash", str(WRAPPER)], env=env, timeout=120,
                           capture_output=True, text=True)
        return p.returncode, self.log()

    def start_stub(self):
        """A live 'capture' the wrapper must recognise (comm=python, matches)."""
        self._procs.append(subprocess.Popen([str(VENV_PY), str(self.stub)]))
        return self._procs[-1]

    # -- fixtures on disk -------------------------------------------------
    def manifest(self, day="2026-08-04", es=1000, mbp1=50000):
        d = self.corpus / day
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({"date": day, "streams": {
            ES: {"cycles": es, "errors": [], "last_pull_utc": "2026-08-04T07:00:00Z"},
            MBP1: {"cycles": mbp1, "errors": [], "last_pull_utc": "2026-08-04T07:00:00Z"},
        }}))

    def seed_frozen_state(self, now=NIGHT, minutes=20, es=1000, mbp1=50000):
        """A previous verdict whose cycle counts match the manifest and whose
        advance timestamps are old — i.e. a capture that has stopped receiving."""
        seen = (datetime.fromisoformat(now).replace(tzinfo=timezone(timedelta(hours=-5)))
                - timedelta(minutes=minutes)).astimezone(timezone.utc)
        stamp = seen.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.corpus.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps({
            "status": "ok", "day": "2026-08-04", "checked_at": stamp,
            "since_utc": stamp, "restarts": 0, "restarts_day": "2026-08-04",
            "streams": {
                ES: {"cycles": es, "advanced_utc": stamp},
                MBP1: {"cycles": mbp1, "advanced_utc": stamp},
            },
        }))

    # -- observing --------------------------------------------------------
    def log(self):
        if not self.logdir.exists():
            return ""
        return "\n".join(f.read_text() for f in sorted(self.logdir.glob("*.log")))

    def has_session(self):
        return subprocess.run(["tmux", "-L", self.socket, "has-session",
                               "-t", self.session], capture_output=True).returncode == 0

    def windows(self):
        r = subprocess.run(["tmux", "-L", self.socket, "list-windows",
                            "-t", self.session, "-F", "#{window_name}"],
                           capture_output=True, text=True)
        return r.stdout.split() if r.returncode == 0 else []

    def pids(self):
        """Live stub processes, with the same comm=python filter the checker
        applies. A bare `pgrep -f` also matches the tmux server, whose argv
        carries the launch command it was started with — exactly the class of
        false positive the filter exists for."""
        r = subprocess.run(["pgrep", "-f", str(self.stub)], capture_output=True, text=True)
        out = []
        for p in r.stdout.split():
            try:
                comm = Path(f"/proc/{p}/comm").read_text().strip()
            except OSError:
                continue
            if comm.startswith("python"):
                out.append(p)
        return out

    def alerts(self):
        if not self.health.exists():
            return []
        return [json.loads(x) for x in self.health.read_text().splitlines() if x.strip()]

    def cleanup(self):
        for p in self._procs:
            p.kill()
            p.wait(timeout=10)
        subprocess.run(["tmux", "-L", self.socket, "kill-server"], capture_output=True)
        subprocess.run(["pkill", "-f", str(self.stub)], capture_output=True)


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    try:
        yield harness
    finally:
        harness.cleanup()


# --- the case the bead exists for ------------------------------------------

def test_dead_capture_is_relaunched(h):
    """02:00, nothing running, GLBX open. This is the death that used to be
    noticed at 08:30 — it must be repaired within one tick."""
    h.manifest()
    rc, log = h.run()
    assert rc == 0, log
    assert "capture is DOWN inside the expected window" in log
    assert "OK: capture relaunched" in log
    assert h.windows() == ["capture"]
    assert len(h.pids()) == 1
    kinds = [a["kind"] for a in h.alerts()]
    assert kinds == ["capture_dead", "capture_restarted"]
    assert json.loads(h.state.read_text())["restarts"] == 1


def test_does_not_relaunch_into_the_last_minute_of_the_window(h):
    """The streamer refuses to start once --until-ct has passed, so a launch at
    23:58 exits instantly and books a phantom restart every night. The rollover
    relaunch after midnight is the one that carries the day."""
    h.manifest()
    rc, log = h.run(now="2026-08-04T23:58")
    assert rc == 0, log
    assert "not relaunching" in log
    assert h.pids() == []
    assert not h.has_session()


def test_bootstraps_a_session_when_the_desk_is_down(h):
    h.manifest()
    assert not h.has_session()
    rc, log = h.run()
    assert rc == 0, log
    assert "bootstrapping a minimal one" in log
    assert h.has_session() and h.windows() == ["capture"]


def test_stale_windows_are_reaped_after_the_fresh_launch(h):
    """st-cm5 ordering: create first, reap after — a session whose only windows
    are stale `capture` windows must never be emptied out of existence."""
    subprocess.run(["tmux", "-L", h.socket, "new-session", "-d",
                    "-s", h.session, "-n", "capture"], check=True)
    h.manifest()
    rc, log = h.run()
    assert rc == 0, log
    assert "reaping stale window" in log
    assert h.windows() == ["capture"]
    assert len(h.pids()) == 1


# --- restraint --------------------------------------------------------------

def test_live_capture_is_left_alone(h):
    proc = h.start_stub()
    h.manifest()
    rc, log = h.run()
    assert rc == 0, log
    assert "no action: ok" in log
    assert proc.poll() is None
    assert not h.has_session()          # no window churn on a no-op
    assert h.alerts() == []


def test_outside_the_window_absence_is_correct(h):
    rc, log = h.run(STRADER_CAPTURE_START_CT="08:30", STRADER_CAPTURE_UNTIL_CT="15:05")
    assert rc == 0, log
    assert "no action: idle" in log
    assert not h.has_session()
    assert h.pids() == []


def test_saturday_absence_is_correct(h):
    rc, log = h.run(now=SATURDAY)
    assert rc == 0, log
    assert "no action: idle" in log
    assert not h.has_session()


def test_duplicate_captures_are_reported_never_killed(h):
    """Two streamers double-append the same JSONL. Which one to stop needs a
    human eye on what each is writing; killing the wrong one loses the tape."""
    a, b = h.start_stub(), h.start_stub()
    h.manifest()
    rc, log = h.run()
    assert rc == 1
    assert "duplicate captures" in log and "NOT killing from cron" in log
    assert a.poll() is None and b.poll() is None
    assert len(h.pids()) == 2            # and no third one launched
    assert h.alerts()[-1]["kind"] == "capture_duplicate"


# --- staleness --------------------------------------------------------------

def test_stale_capture_alerts_but_is_left_running_by_default(h):
    proc = h.start_stub()
    h.manifest()
    h.seed_frozen_state()
    rc, log = h.run()
    assert rc == 1
    assert "alive but not receiving" in log
    assert "killing from cron stays a human call" in log
    assert proc.poll() is None
    assert h.alerts()[-1]["kind"] == "capture_stale"


def test_stale_capture_is_recycled_when_the_operator_opts_in(h):
    proc = h.start_stub()
    h.manifest()
    h.seed_frozen_state()
    rc, log = h.run(STRADER_CAPTURE_RESTART_STALE="1")
    assert rc == 0, log
    assert "terminating" in log and "OK: capture relaunched" in log
    assert proc.poll() is not None       # the frozen one was stopped
    assert len(h.pids()) == 1            # exactly one capture afterwards
    assert h.windows() == ["capture"]


def test_partial_staleness_never_recycles(h):
    """One frozen worker while another still receives is alertable but not
    unambiguous; a needless kill of a half-working capture costs real data."""
    proc = h.start_stub()
    h.manifest(es=1000, mbp1=77777)      # mbp1 moved on from the seeded state
    h.seed_frozen_state()
    rc, log = h.run(STRADER_CAPTURE_RESTART_STALE="1")
    assert rc == 1
    assert "partial staleness" in log
    assert proc.poll() is None


# --- infrastructure ---------------------------------------------------------

def test_missing_venv_python_is_fatal(h):
    rc, log = h.run(STRADER_PY="/nonexistent/python")
    assert rc == 2
    assert "FATAL: venv python not executable" in log


def test_unparseable_verdict_is_fatal_not_silent(h):
    """A checker that cannot answer must not read as 'nothing to do'."""
    fake = h.tmp / "broken_check.py"
    fake.write_text("import sys\nsys.exit(3)\n")
    rc, log = h.run(STRADER_REPO=str(h.tmp))
    assert rc == 2
    assert "FATAL" in log
