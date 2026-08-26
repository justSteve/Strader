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


# ── defence 3: "asked and told no" is an answer, not a miss [st-9cp0] ───────
#
# The 2026-08-26 00:42 failure: "GEX collector UP 00:00 via argv scan" while the
# unit was correctly inactive outside the RTH gate and _gexbot_health.json said
# IDLE. `probe` asked systemd, got the right answer, then fell through to the
# argv scan anyway — where any short-lived process carrying the script's name
# wins. etime 00:00 is the signature: a collector is never zero seconds old.
#
# Harmless at 00:42. Inside 08:30-15:05 it is a green row over a dead feed, at
# the only hours it matters.

# A repo search carrying the script name. The search binary is not called
# "grep", so neither `grep -v grep` nor LAUNCHER_RE excludes it — which is why
# widening LAUNCHER_RE is not the fix.
SEARCHER = ("9001 00:00 /root/.local/share/claude/2.1.233 --search "
            "corpus_poll_gexbot.py /root/projects/Strader")
REAL_GEX = ("9002 01:23:45 /root/projects/Strader/.venv/bin/python3 "
            "scripts/corpus_poll_gexbot.py --day 2026-08-26")


def _run_with_systemd(tmp_path, *lines, active_pid: str | None = None):
    """Run with a stub systemctl on PATH, so the supervisor is REACHABLE.

    A stub rather than a new production env-var seam: the point is to exercise
    the real `systemd_reachable` / `unit_pid` path, and a seam that only tests
    use is a seam that can drift from what production does.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = "active" if active_pid else "inactive"
    (bin_dir / "systemctl").write_text(textwrap.dedent(f"""\
        #!/bin/bash
        # show <unit> -p <Prop> --value
        for a in "$@"; do
          case "$a" in
            ActiveState) echo "{state}"; exit 0 ;;
            MainPID)     echo "{active_pid or 0}"; exit 0 ;;
          esac
        done
        exit 0
    """))
    (bin_dir / "systemctl").chmod(0o755)

    fixture = tmp_path / "ps.txt"
    fixture.write_text("\n".join(lines) + "\n")
    out = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True, text=True, cwd=str(REPO),
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": "/root",
             "LIVENESS_PS_FIXTURE": str(fixture)},
    )
    return out.stdout


def test_an_inactive_unit_is_down_even_when_a_process_names_the_script(tmp_path):
    """THE 00:42 REGRESSION. The supervisor was asked and said no; that is the
    answer. A searcher mentioning the script must not turn the row green."""
    row = _row(_run_with_systemd(tmp_path, SEARCHER), "GEX collector")
    assert " DOWN " in row, row
    assert " UP " not in row
    assert "argv scan" not in row, "a unit-backed row must not fall back to argv"


def test_the_argv_match_is_demoted_not_discarded(tmp_path):
    """A hand-started run stays visible to a human without ever being green."""
    row = _row(_run_with_systemd(tmp_path, SEARCHER), "GEX collector")
    assert "NOT SUPERVISOR-CONFIRMED" in row
    assert "9001" in row, "the pid a human would go look at is named"


def test_an_active_unit_still_reads_up(tmp_path):
    """Defence 3 must not make every unit-backed row permanently DOWN."""
    row = _row(_run_with_systemd(tmp_path, REAL_GEX, active_pid="9002"),
               "GEX collector")
    assert " UP " in row, row
    assert "9002" in row


def test_a_unitless_row_still_uses_the_argv_scan(tmp_path):
    """The fallback is not removed — it is scoped to rows with no unit, which
    is what the file's header always said it was for."""
    row = _row(_run_with_systemd(
        tmp_path,
        "9500 00:31:00 /root/projects/Strader/.venv/bin/python3 "
        "scripts/gexbot_hist_backfill.py --day 2026-08-25"), "GEX hist backfill")
    assert " UP " in row and "argv scan" in row, row


def test_an_unreachable_supervisor_still_falls_back(tmp_path):
    """No systemd means no supervisor to ask, so argv is the only answer left.
    This is the case LIVENESS_NO_SYSTEMD models and it must keep working."""
    row = _row(_run(tmp_path, REAL_GEX), "GEX collector")
    assert " UP " in row and "argv scan" in row, row


def test_widening_the_launcher_pattern_is_not_the_fix(tmp_path):
    """Documents WHY defence 3 is structural rather than another denylist entry.

    The searcher is excluded by neither `grep -v grep` nor LAUNCHER_RE, because
    the search binary is named after a version number. Any such list has no
    completion — the same defect st-hd51 retired one layer up."""
    assert "grep" not in SEARCHER
    for pat in ("tmux", "new-session", "send-keys", "surface_liveness.sh"):
        assert pat not in SEARCHER
