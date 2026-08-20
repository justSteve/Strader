"""A launcher must never be mistaken for the thing it launches. [st-cc5k]

The 2026-08-14 failure: `surface_liveness.sh` reported "ES capture UP · pid
133436 · uptime 1-23:03:08" for two days. 133436 was a leftover tmux CLIENT
from 08-12 whose argv still carried the capture command line — it had outlived
the window it created. The probe matched on script NAME and took the lowest
pid, so the stale client won. Had the real capture died, the row would have
stayed GREEN indefinitely.

The bead asks for exactly this control case: a process whose args merely MENTION
the script must not read UP.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "surface_liveness.sh"

# The real 2026-08-12 tmux client argv, trimmed. It mentions the capture script
# but is a launcher, not the capture.
LAUNCHER = ("133436 1-23:03:08 tmux -L moocity new-session -d -s steves-desk "
            "-n capture exec env PYTHONPATH=/root/projects/Strader "
            "python3 scripts/corpus_stream_databento.py --streams es,es-mbp1")
REAL = ("2560777 12:41:02 /root/projects/Strader/.venv/bin/python3 "
        "scripts/corpus_stream_databento.py --streams es,es-mbp1 --now")


def _run(tmp_path: Path, *lines: str) -> str:
    fixture = tmp_path / "ps.txt"
    fixture.write_text("\n".join(lines) + "\n")
    out = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True, text=True, cwd=str(REPO),
        env={"PATH": "/usr/bin:/bin", "HOME": "/root",
             "LIVENESS_PS_FIXTURE": str(fixture),
             "LIVENESS_NO_SYSTEMD": "1"},
    )
    return out.stdout


def _row(output: str, label: str) -> str:
    for line in output.splitlines():
        if line.startswith(label):
            return line
    raise AssertionError(f"no {label!r} row in:\n{output}")


def test_launcher_alone_does_not_read_up(tmp_path):
    """THE CONTROL CASE. A tmux client mentioning the script is not the script."""
    row = _row(_run(tmp_path, LAUNCHER), "ES capture")
    assert " DOWN " in row, row
    assert "133436" not in row, "the stale tmux client was reported as the capture"


def test_real_process_reads_up(tmp_path):
    row = _row(_run(tmp_path, REAL), "ES capture")
    assert " UP " in row, row
    assert "2560777" in row


def test_launcher_does_not_win_over_the_real_process(tmp_path):
    """The launcher has the LOWER pid, which is how it won under `head -1`."""
    row = _row(_run(tmp_path, LAUNCHER, REAL), "ES capture")
    assert " UP " in row, row
    assert "2560777" in row, row
    assert "133436" not in row, "lowest-pid-wins regression"


def test_row_names_the_source_that_answered(tmp_path):
    """A wrong green must be diagnosable without a ps archaeology session."""
    row = _row(_run(tmp_path, REAL), "ES capture")
    assert "via argv scan" in row, row


def test_absent_process_reads_down(tmp_path):
    row = _row(_run(tmp_path, "999 01:00 /usr/bin/python3 something_else.py"),
               "ES capture")
    assert " DOWN " in row, row
