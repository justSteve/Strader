"""mancini-preopen-wrapper.sh — the feeder anchor reconciliation block. [st-kxnv]

THE BUG THIS GUARDS. The live feeder loads the day's Mancini set once at start
(live_footprint_feed.py:468) and its unit restarts at the CT midnight rollover,
hours before the letter is parsed. Measured from the live-parity run rows
2026-08-21..27, every day recorded ZERO anchors except 08-24, which was a hand
restart. A session with no anchors emits no plan-level events about Steve's own
levels: 08-25 produced 570 rows of which 7 were Level events.

The block restarts the feeder only when the day's levels exist AND the running
process recorded none of them. Two properties are worth a test each:

  * the probe never guesses — an absent, empty, truncated or unreadable parity
    file resolves to "skip", never to "restart". This job bounces a LIVE feed;
    a restart on a bad read is worse than the bug it fixes.
  * the shell honours the probe — including refusing to touch a unit that is
    deliberately stopped, and alerting rather than failing silent when the
    restart itself fails.

Both halves are EXTRACTED FROM THE SHIPPING WRAPPER at test time rather than
copied here, so a future edit to the block cannot leave this file passing
against text that no longer runs.

`systemctl` is stubbed on PATH and STRADER_CORPUS_ROOT redirects the health log
into tmp_path, so nothing here touches the live unit or fires a real alert.
"""
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "cron" / "mancini-preopen-wrapper.sh"
DAY = datetime.date.today().isoformat()

#: The interpreter the shipping block is handed as $PY. The wrapper itself
#: resolves the repo venv in production; here we prefer it when it exists so the
#: test matches the live invocation, and fall back to the interpreter running
#: the tests so the block is still genuinely exercised elsewhere.
_VENV_PY = REPO / ".venv" / "bin" / "python"
_PY = _VENV_PY if _VENV_PY.exists() else Path(sys.executable)


def _wrapper_text() -> str:
    if not WRAPPER.exists():
        pytest.skip(f"wrapper not present: {WRAPPER}")
    return WRAPPER.read_text()


def probe_source() -> str:
    """The python heredoc inside the reconciliation block, as it ships."""
    text = _wrapper_text()
    start = text.index("# ── feeder anchor reconciliation")
    block = text[start:]
    m = re.search(r"<<'PYEOF'\n(.*?)\nPYEOF\n", block, re.S)
    if not m:
        pytest.skip("reconciliation probe heredoc not found — block was restructured")
    return m.group(1)


def block_source() -> str:
    """The reconciliation block itself, from its banner to the wrapper's exit."""
    text = _wrapper_text()
    start = text.index("# ── feeder anchor reconciliation")
    end = text.index("\n    exit $rc", start)
    return text[start:end]


def row(k, **kw):
    return json.dumps({"k": k, **kw}) + "\n"


def _corpus(tmp_path, *, levels, parity_lines, parity_is_dir=False):
    """A throwaway repo-shaped tree; returns its root."""
    root = tmp_path / "repo"
    (root / "runbook/mancini/commentary").mkdir(parents=True)
    (root / "data/derived/live-parity").mkdir(parents=True)
    if levels:
        (root / f"runbook/mancini/commentary/{DAY}.jsonl").write_text("{}\n")
    parity = root / f"data/derived/live-parity/{DAY}.jsonl"
    if parity_is_dir:
        parity.mkdir()
    elif parity_lines is not None:
        parity.write_text("".join(parity_lines))
    return root


# --------------------------------------------------------------------- probe

@pytest.mark.parametrize("name,kwargs,expect", [
    # the two states that matter on a normal morning
    ("levels parsed, feeder anchorless",
     dict(levels=True, parity_lines=[row("run", mancini=[])]), "restart anchors=0"),
    ("levels parsed, feeder already holds them",
     dict(levels=True, parity_lines=[row("run", mancini=[1.0, 2.0])]), "ok anchors=2"),
    # the parse has not run yet: nothing to load, so nothing to restart for
    ("no levels parsed yet",
     dict(levels=False, parity_lines=[row("run", mancini=[])]), "skip no-levels-parsed-yet"),
    # the LAST run row is the running process; an earlier bad one is history
    ("a later good run supersedes an earlier anchorless one",
     dict(levels=True, parity_lines=[row("run", mancini=[]), row("ev", kind="x"),
                                     row("run", mancini=[1.0])]), "ok anchors=1"),
    ("a later anchorless run supersedes an earlier good one",
     dict(levels=True, parity_lines=[row("run", mancini=[1.0]), row("run", mancini=[])]),
     "restart anchors=0"),
    # a live feed is never bounced on a bad read
    ("no parity file at all",
     dict(levels=True, parity_lines=None), "skip parity-unreadable(FileNotFoundError)"),
    ("parity path is not a file",
     dict(levels=True, parity_lines=None, parity_is_dir=True),
     "skip parity-unreadable(IsADirectoryError)"),
    ("parity file holds no run row",
     dict(levels=True, parity_lines=[row("ev", kind="x")]), "skip no-run-row"),
    ("empty parity file",
     dict(levels=True, parity_lines=[]), "skip no-run-row"),
    # the feeder appends while we read: a half-written last line is ordinary
    ("a truncated trailing line is skipped, not fatal",
     dict(levels=True, parity_lines=['{"k": "run", "manc\n', row("run", mancini=[3.0])]),
     "ok anchors=1"),
    # a run row that never recorded the field reads the same as zero anchors
    ("mancini key absent",
     dict(levels=True, parity_lines=[row("run")]), "restart anchors=0"),
    ("mancini null",
     dict(levels=True, parity_lines=[row("run", mancini=None)]), "restart anchors=0"),
])
def test_probe_verdict(tmp_path, name, kwargs, expect):
    root = _corpus(tmp_path, **kwargs)
    out = subprocess.run([sys.executable, "-c", probe_source()], cwd=root,
                         capture_output=True, text=True)
    assert out.stdout.strip() == expect, f"{name}: stderr={out.stderr}"


# --------------------------------------------------------------------- shell

@pytest.fixture
def shell(tmp_path):
    """Runs the shipping block with systemctl stubbed and the health log redirected."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "systemctl"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$1\" in\n"
        "  is-active) [[ \"${STUB_ACTIVE:-1}\" == 1 ]] && exit 0 || exit 3 ;;\n"
        "  restart)   echo \"STUB: restart $2\" >&2; exit \"${STUB_RESTART_RC:-0}\" ;;\n"
        "esac\nexit 0\n")
    stub.chmod(0o755)
    block = tmp_path / "block.sh"
    block.write_text(block_source())

    def run(root, **env_overrides):
        env = {**os.environ,
               "PATH": f"{bin_dir}:{os.environ['PATH']}",
               "STRADER_REPO": str(REPO),
               # keeps emit_alert's health log out of the real corpus
               "STRADER_CORPUS_ROOT": str(tmp_path / "corpus"),
               # The repo venv on Steve's box; the running interpreter anywhere
               # else. Hardcoding .venv made all three of these tests resolve to
               # "skip probe-failed" on any box without one — CI included, where
               # the package is pip-installed into the runner's own Python — and
               # a probe that cannot run reads exactly like a probe that ran and
               # declined. [st-v55j]
               "PY": str(_PY),
               **env_overrides}
        return subprocess.run(
            ["bash", "-c", 'log() { echo "$*"; }; source "$1"', "_", str(block)],
            cwd=root, env=env, capture_output=True, text=True).stdout

    return run


@pytest.fixture
def anchorless(tmp_path):
    return _corpus(tmp_path, levels=True, parity_lines=[row("run", mancini=[])])


def test_restarts_when_the_feeder_is_anchorless(shell, anchorless):
    out = shell(anchorless, STUB_ACTIVE="1", STUB_RESTART_RC="0")
    assert "feeder reconciliation: restart anchors=0" in out
    assert "restarted strader-footprint-feed" in out


def test_leaves_a_healthy_feeder_alone(shell, tmp_path):
    root = _corpus(tmp_path, levels=True, parity_lines=[row("run", mancini=[1.0, 2.0])])
    out = shell(root, STUB_ACTIVE="1")
    assert "ok anchors=2" in out
    assert "restarted" not in out


def test_never_starts_a_unit_that_is_deliberately_stopped(shell, anchorless):
    """A stopped feeder is somebody's decision; cron does not overrule it."""
    out = shell(anchorless, STUB_ACTIVE="0")
    assert "is not active — leaving it alone" in out
    assert "restarted" not in out


def test_env_switch_disables_the_restart(shell, anchorless):
    out = shell(anchorless, STRADER_FEEDER_RESTART="0")
    assert "disabled by STRADER_FEEDER_RESTART" in out
    assert "restarted" not in out


def test_a_failed_restart_alerts_rather_than_failing_silent(shell, anchorless, tmp_path):
    out = shell(anchorless, STUB_ACTIVE="1", STUB_RESTART_RC="1")
    assert "ERROR: restart of" in out
    health = tmp_path / "corpus" / "_health.jsonl"
    assert health.exists(), "a failed restart must leave a durable alert"
    rows = [json.loads(x) for x in health.read_text().splitlines() if x.strip()]
    assert [r for r in rows if r.get("kind") == "feeder_anchors"]


def test_the_alert_never_lands_in_the_real_corpus_health_log(shell, anchorless):
    """The harness itself is the thing under test here: an earlier version of
    this file appended a live alert row that the gate and the morning heartbeat
    both read."""
    real = REPO / "data" / "corpus" / "_health.jsonl"
    before = real.read_text() if real.exists() else ""
    shell(anchorless, STUB_ACTIVE="1", STUB_RESTART_RC="1")
    after = real.read_text() if real.exists() else ""
    assert before == after
