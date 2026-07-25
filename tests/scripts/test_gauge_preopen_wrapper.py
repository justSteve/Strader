"""gauge-preopen-wrapper.sh — session-window and desk-bootstrap paths.

st-5n8: outside 08:00–15:15 CT Mon–Fri, "no gauge running" is the CORRECT
state; the heartbeat must not respawn one. A gauge that outlived the window is
reported, never killed from cron.

st-r3f: a down desk is brought up by COO's REAL bootstrap; the 7/23 minimal
session is the fallback, not the first choice.

Every case runs on a throwaway tmux socket with a python stub standing in for
the gauge (STRADER_GAUGE_MATCH / _LAUNCH), so nothing here touches the moocity
desk or the gated live Schwab API.
"""
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "cron" / "gauge-preopen-wrapper.sh"
VENV_PY = REPO / ".venv" / "bin" / "python"

FRI_OPEN = "2026-07-24T10:00"     # Friday, mid-session
FRI_PRE = "2026-07-24T08:00"      # Friday, first heartbeat (pre-open)
FRI_LATE = "2026-07-24T16:00"     # Friday, after the 15:15 stop
SAT = "2026-07-25T10:00"          # Saturday — the day the 7/24 run was found on

pytestmark = pytest.mark.skipif(
    not shutil.which("tmux") or not VENV_PY.exists(),
    reason="needs tmux and the repo venv",
)


class Harness:
    def __init__(self, tmp_path):
        self.tag = uuid.uuid4().hex[:10]
        self.socket = f"strader-t-{self.tag}"
        self.session = f"scratch-{self.tag}"
        self.logdir = tmp_path / "logs"
        self.marker = tmp_path / "desk-bootstrap-ran"
        self.stub = tmp_path / f"gauge_stub_{self.tag}.py"
        self.stub.write_text("import time\nwhile True:\n    time.sleep(1)\n")
        self.bootstrap = tmp_path / "fake-steves-desk-session.sh"
        self.bootstrap.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'SOCK="${TMUX_SOCKET:-moocity}"\n'
            f'printf "%s\\n" "$SOCK" >> "{self.marker}"\n'
            'if tmux -L "$SOCK" has-session -t steves-desk 2>/dev/null; then exit 0; fi\n'
            'tmux -L "$SOCK" new-session -d -s steves-desk -n System\n'
            'tmux -L "$SOCK" new-window  -d -t steves-desk -n Trading\n'
            'tmux -L "$SOCK" new-window  -d -t steves-desk -n Logs\n'
        )
        self.bootstrap.chmod(0o755)
        self._procs = []

    # -- driving ---------------------------------------------------------
    def run(self, now, session=None, bootstrap=None, **extra):
        env = dict(os.environ)
        env.update({
            "STRADER_TMUX_SOCKET": self.socket,
            "STRADER_TMUX_SESSION": session or self.session,
            "STRADER_GAUGE_WIN": "gauge",
            "STRADER_ANCHOR_WIN": "Trading",
            "STRADER_GAUGE_MATCH": str(self.stub),
            "STRADER_GAUGE_LAUNCH": f"exec {VENV_PY} {self.stub}",
            "STRADER_GAUGE_LOGDIR": str(self.logdir),
            "STRADER_GAUGE_NOW": now,
            "STRADER_DESK_BOOTSTRAP": str(bootstrap) if bootstrap else "/nonexistent/desk.sh",
        })
        env.update(extra)
        p = subprocess.run(["bash", str(WRAPPER)], env=env, timeout=90,
                           capture_output=True, text=True)
        return p.returncode, self.log()

    def start_stub(self):
        """A live 'gauge' the wrapper must recognise (comm=python, matches)."""
        self._procs.append(subprocess.Popen([str(VENV_PY), str(self.stub)]))
        return self._procs[-1]

    # -- observing -------------------------------------------------------
    def log(self):
        if not self.logdir.exists():
            return ""
        return "\n".join(f.read_text() for f in sorted(self.logdir.glob("*.log")))

    def has_session(self, session=None):
        return subprocess.run(
            ["tmux", "-L", self.socket, "has-session", "-t", session or self.session],
            capture_output=True).returncode == 0

    def windows(self, session=None):
        r = subprocess.run(
            ["tmux", "-L", self.socket, "list-windows",
             "-t", session or self.session, "-F", "#{window_name}"],
            capture_output=True, text=True)
        return r.stdout.split() if r.returncode == 0 else []

    def gauge_pids(self):
        r = subprocess.run(["pgrep", "-f", str(self.stub)],
                           capture_output=True, text=True)
        return [p for p in r.stdout.split() if p]

    def cleanup(self):
        for p in self._procs:
            p.kill()
            p.wait(timeout=10)
        subprocess.run(["tmux", "-L", self.socket, "kill-server"],
                       capture_output=True)
        subprocess.run(["pkill", "-f", str(self.stub)], capture_output=True)


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    try:
        yield harness
    finally:
        harness.cleanup()


# --- st-5n8: the session window -------------------------------------------

def test_after_session_end_no_launch(h):
    """16:00 Friday. The heartbeat still fires (cron runs to 15:55) but must
    treat an absent gauge as correct — this is the launch that produced the
    26-hour 7/24 run."""
    rc, log = h.run(FRI_LATE)
    assert rc == 0
    assert "outside the session window" in log
    assert not h.has_session()
    assert h.gauge_pids() == []


def test_weekend_no_launch(h):
    rc, log = h.run(SAT)
    assert rc == 0
    assert "outside the session window" in log
    assert not h.has_session()


def test_before_session_start_no_launch(h):
    rc, log = h.run("2026-07-24T07:55")
    assert rc == 0
    assert "outside the session window" in log
    assert not h.has_session()


def test_survivor_outside_the_window_is_warned_not_killed(h):
    """A pre-fix gauge still alive on Saturday: report it, leave it. Killing
    someone's process from cron is not this script's call."""
    proc = h.start_stub()
    rc, log = h.run(SAT)
    assert rc == 0
    assert "WARN" in log and "OUTSIDE" in log
    assert "Not killing from cron" in log
    assert proc.poll() is None            # still alive
    assert not h.has_session()            # and no second one spawned


def test_pre_open_launch_still_happens(h):
    """08:00 is inside the window — the pre-open launch that gives the
    cum-TICK spine full-session semantics must be unaffected."""
    rc, log = h.run(FRI_PRE, session="steves-desk", bootstrap=h.bootstrap)
    assert rc == 0, log
    assert "OK: launched live gauge" in log
    assert "gauge" in h.windows("steves-desk")


def test_in_session_idempotent_noop(h):
    h.start_stub()
    rc, log = h.run(FRI_OPEN)
    assert rc == 0
    assert "live gauge already running" in log
    assert not h.has_session()            # no window churn on a no-op
    assert not h.marker.exists()          # and no desk bootstrap either


# --- st-r3f: bring up the REAL desk ---------------------------------------

def test_down_desk_starts_the_real_desk(h):
    """Desk down + real bootstrap available → invoke it, then land the gauge
    in the actual surface, inserted after the Trading anchor."""
    rc, log = h.run(FRI_OPEN, session="steves-desk", bootstrap=h.bootstrap)
    assert rc == 0, log
    assert "invoking COO desk bootstrap" in log
    assert "real desk is up" in log
    assert h.marker.exists()
    assert h.marker.read_text().strip() == h.socket   # honoured our socket
    # Real desk windows are present and the gauge sits right after Trading.
    wins = h.windows("steves-desk")
    assert wins == ["System", "Trading", "gauge", "Logs"], wins
    assert len(h.gauge_pids()) == 1


def test_real_desk_bootstrap_not_called_when_desk_is_up(h):
    """It is idempotent, but the cheapest call is the one not made."""
    subprocess.run(["tmux", "-L", h.socket, "new-session", "-d",
                    "-s", "steves-desk", "-n", "Trading"], check=True)
    rc, log = h.run(FRI_OPEN, session="steves-desk", bootstrap=h.bootstrap)
    assert rc == 0, log
    assert not h.marker.exists()
    assert h.windows("steves-desk") == ["Trading", "gauge"]


def test_falls_back_to_minimal_when_real_bootstrap_missing(h):
    """The 7/23 behaviour is preserved as the fallback, not deleted."""
    rc, log = h.run(FRI_OPEN, session="steves-desk", bootstrap="/nonexistent/desk.sh")
    assert rc == 0, log
    assert "not usable" in log
    assert "bootstrapping a minimal session" in log
    assert h.windows("steves-desk") == ["gauge"]


def test_falls_back_to_minimal_when_real_bootstrap_fails(h, tmp_path):
    broken = tmp_path / "broken-desk.sh"
    broken.write_text("#!/usr/bin/env bash\nexit 3\n")
    broken.chmod(0o755)
    rc, log = h.run(FRI_OPEN, session="steves-desk", bootstrap=broken)
    assert rc == 0, log
    assert "WARN: desk bootstrap produced no session" in log
    assert "bootstrapping a minimal session" in log
    assert h.windows("steves-desk") == ["gauge"]


def test_non_desk_session_name_skips_real_bootstrap(h):
    """COO's script only ever creates 'steves-desk'; pointing it at another
    name would build the wrong session."""
    rc, log = h.run(FRI_OPEN, bootstrap=h.bootstrap)
    assert rc == 0, log
    assert "not usable" in log
    assert not h.marker.exists()
    assert h.windows() == ["gauge"]


def test_stale_windows_reaped_after_fresh_launch(h):
    """st-cm5 invariant: create first, then reap — the session is never empty."""
    subprocess.run(["tmux", "-L", h.socket, "new-session", "-d",
                    "-s", h.session, "-n", "gauge"], check=True)
    rc, log = h.run(FRI_OPEN)
    assert rc == 0, log
    assert "reaping stale window" in log
    assert h.windows() == ["gauge"]
    assert len(h.gauge_pids()) == 1


def test_session_end_is_exported_to_the_gauge(h):
    """Wrapper and gauge must stop on the same number — one source of truth,
    so the no-respawn window can never drift from the self-exit time."""
    rc, log = h.run(FRI_OPEN)
    assert rc == 0, log
    pid = h.gauge_pids()[0]
    launched_env = Path(f"/proc/{pid}/environ").read_bytes().decode().split("\0")
    assert "STRADER_GAUGE_SESSION_END=15:15" in launched_env
