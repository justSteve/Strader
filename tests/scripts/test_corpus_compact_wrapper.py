"""corpus-compact-wrapper.sh — the gate's verdict decides, and the trailing
sweep packs what an earlier morning left raw. [co-8b60y]

Until 2026-09-04 the wrapper kept its own rule ("any error → skip") and looked
only at the most recent session day, so one reconnect note left a day raw for
good and the 09-02/03 outage left 7 GB of whole tape unpacked. Every case here
runs against a tmp corpus root (STRADER_CORPUS_ROOT) with a pinned clock
(STRADER_COMPACT_NOW), the real compactor and the real gate; nothing touches
data/corpus.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "cron" / "corpus-compact-wrapper.sh"
VENV_PY = REPO / ".venv" / "bin" / "python"

ES = "databento_glbx_es"
SATURDAY = "2026-09-05T07:30"       # most recent session day = Fri 2026-09-04

pytestmark = pytest.mark.skipif(not VENV_PY.exists(), reason="needs the repo venv")

RECONNECT = "reconnect #{n}: BentoError: Gateway timeout: 40 second(s) since last message (possible gap)"


class Corpus:
    def __init__(self, tmp_path: Path):
        self.root = tmp_path / "corpus"
        self.root.mkdir()
        self.logdir = tmp_path / "logs"

    def day(self, day: str, *, manifest=True, cycles=1000, errors=(),
            last_pull="T20:05:00Z", raw=True):
        d = self.root / day
        d.mkdir(parents=True, exist_ok=True)
        if raw:
            (d / f"{ES}.0.dbn").write_bytes(b"\x00\x01DBN\xff" * 5000)
            (d / f"{ES}.jsonl").write_text('{"x":1}\n' * 2000)
        if manifest:
            (d / "manifest.json").write_text(json.dumps({
                "date": day,
                "streams": {ES: {"cycles": cycles, "errors": list(errors),
                                 "last_pull_utc": day + last_pull}}}))
        return d

    def run(self, now=SATURDAY, **extra):
        env = dict(os.environ)
        env.update({
            "HB_STATE_DIR": str(self.logdir / "state"),   # never the live /var/moo/state
            "STRADER_CORPUS_ROOT": str(self.root),
            "STRADER_COMPACT_LOGDIR": str(self.logdir),
            "STRADER_COMPACT_NOW": now,
        })
        env.update(extra)
        p = subprocess.run(["bash", str(WRAPPER)], env=env, timeout=300,
                           capture_output=True, text=True)
        return p.returncode, self.log()

    def log(self) -> str:
        if not self.logdir.exists():
            return ""
        return "\n".join(f.read_text() for f in sorted(self.logdir.glob("*.log")))

    def raw(self, day: str) -> list[str]:
        d = self.root / day
        return sorted(p.name for p in d.glob("databento_*.dbn")) + \
            sorted(p.name for p in d.glob("databento_*.jsonl"))

    def packed(self, day: str) -> list[str]:
        d = self.root / day
        return sorted(p.name for p in d.glob("databento_*.zst")) + \
            sorted(p.name for p in d.glob("databento_*.gz"))


@pytest.fixture
def c(tmp_path):
    return Corpus(tmp_path)


def test_covered_day_with_reconnect_notes_packs(c):
    """The finding of 2026-09-04: whole tape, past the close, many transport
    notes. The old rule skipped it forever; the gate passes it and it packs."""
    c.day("2026-09-04", errors=[RECONNECT.format(n=i) for i in range(1, 11)])
    rc, log = c.run()
    assert rc == 0, log
    assert "target day = 2026-09-04" in log and "packed 2026-09-04" in log
    assert "DEGRADED" in log and "reconnected 10 times" in log
    assert c.raw("2026-09-04") == []
    assert c.packed("2026-09-04") == [f"{ES}.0.dbn.zst", f"{ES}.jsonl.gz"]
    assert "packed=1 failed=0 skipped=0" in log


def test_uncovered_day_is_skipped_with_the_gates_reason(c):
    c.day("2026-09-04", last_pull="T17:16:04Z")          # died 12:16 CT
    rc, log = c.run()
    assert rc == 0, log
    assert "skip — 2026-09-04: " in log and "stopped before 2026-09-04 closed" in log
    assert c.raw("2026-09-04") == [f"{ES}.0.dbn", f"{ES}.jsonl"]
    assert c.packed("2026-09-04") == []
    assert "(rc=0; packed=0 failed=0 skipped=1)" in log


def test_a_real_error_is_skipped(c):
    c.day("2026-09-04", errors=["disk full: write failed"])
    rc, log = c.run()
    assert rc == 0, log
    assert "skip — 2026-09-04: stream 'databento_glbx_es' reported 1 error(s)" in log
    assert c.packed("2026-09-04") == []


def test_no_manifest_is_a_skip(c):
    c.day("2026-09-04", manifest=False)
    rc, log = c.run()
    assert rc == 0, log
    assert "skip — 2026-09-04: no manifest" in log
    assert c.raw("2026-09-04") != []


def test_sweep_packs_older_raw_days_the_gate_passes_and_leaves_the_rest(c):
    """Saturday 07:30 after the outage week: Friday healthy, Thursday uncovered,
    Wednesday whole with notes, Tuesday a real error, Monday no manifest, the
    Sunday segments untouched (not a session), and a healthy day 10 days back
    outside the window untouched."""
    c.day("2026-09-04")
    c.day("2026-09-03", last_pull="T17:16:04Z")
    c.day("2026-09-02", errors=[RECONNECT.format(n=i) for i in range(1, 2926)])
    c.day("2026-09-01", errors=["disk full: write failed"])
    c.day("2026-08-31", manifest=False)
    c.day("2026-08-30")                                      # Sunday
    c.day("2026-08-26")                                      # outside 7 days
    rc, log = c.run()
    assert rc == 0, log
    lines = [l for l in log.splitlines() if l.startswith(("packed ", "skip — "))]
    assert lines == [
        "packed 2026-09-04",
        "skip — 2026-09-03: stream 'databento_glbx_es' stopped before 2026-09-03 closed: "
        "last pull 2026-09-03T17:16:04Z, 154 min short of the 15:00 CT close. "
        "The day has a hole in it — this is not a staleness warning.",
        "packed 2026-09-02",
        "skip — 2026-09-01: stream 'databento_glbx_es' reported 1 error(s)",
        "skip — 2026-08-31: no manifest",
    ], lines
    assert c.packed("2026-09-04") and c.packed("2026-09-02")
    assert c.raw("2026-09-04") == [] and c.raw("2026-09-02") == []
    for untouched in ("2026-09-03", "2026-09-01", "2026-08-31", "2026-08-30", "2026-08-26"):
        assert c.raw(untouched) == [f"{ES}.0.dbn", f"{ES}.jsonl"], untouched
        assert c.packed(untouched) == [], untouched
    assert "packed=2 failed=0 skipped=3" in log


def test_sweep_window_is_configurable(c):
    c.day("2026-09-04", raw=False)
    c.day("2026-08-26")
    rc, log = c.run(STRADER_COMPACT_SWEEP_DAYS="14")
    assert rc == 0, log
    assert "packed 2026-08-26" in log


def test_nothing_raw_is_a_quiet_no_op(c):
    c.day("2026-09-04", raw=False)
    rc, log = c.run()
    assert rc == 0, log
    assert "nothing raw in the last 7 day(s)" in log and "(rc=0, no-op)" in log


def test_a_pack_failure_is_rc1_and_leaves_the_source(c, tmp_path):
    """The compactor refuses (rc 3) when the archive does not verify; the
    wrapper reports it and exits 1 so the unit result shows it."""
    c.day("2026-09-04")
    fake_repo = tmp_path / "repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "scripts" / "corpus_compact_databento.py").write_text(
        "import sys\nprint('[ALERT] archive failed verification', file=sys.stderr)\nsys.exit(3)\n")
    # the vetting still needs the real packages: point PYTHONPATH at them via
    # a sitecustomize-free trick — symlink the two packages into the fake repo
    for pkg in ("market", "runbook", "strader"):
        (fake_repo / pkg).symlink_to(REPO / pkg)
    rc, log = c.run(STRADER_REPO=str(fake_repo), STRADER_PY=str(VENV_PY))
    assert rc == 1, log
    assert "FAILED 2026-09-04 (rc=3)" in log and "source left in place" in log
    assert c.raw("2026-09-04") == [f"{ES}.0.dbn", f"{ES}.jsonl"]


def test_missing_venv_python_is_fatal(c):
    rc, log = c.run(STRADER_PY="/nonexistent/python")
    assert rc == 2
    assert "FATAL: venv python not executable" in log
