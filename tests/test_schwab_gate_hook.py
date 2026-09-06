"""Schwab gate hook — behaviour tests, including the nesting control. [st-ad6p]

THE CONTROL CASE IS THE POINT (COO, 2026-08-13). A test that only proves the
gate fires does not prove the gate reads the right key: the live hook parsed the
bare `.command` instead of the nested `.tool_input.command`, so every gate had
been silently allowing everything since May while looking perfectly correct.

So every blocking case is asserted twice:
  - nested payload (the real PreToolUse shape) -> BLOCKS
  - the same command at the TOP LEVEL only     -> a hook reading only the
    nested key must not see it
That second assertion is what would have caught the original defect, and it is
what catches a regression back to the bare form.

Points at the live hook — the fix was installed 2026-08-13 with Steve's approval.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "scripts" / "schwab-gate.sh"

# The gate reads the named file's imports and SKIPS a file that is not there
# (`[ -f "$PY_FILE" ] || continue`), so a case naming a production script
# becomes an allow the day that script is deleted — a green suite over an
# open gate. The behavioural cases below name fixtures that exist only to be
# read; the live estate is covered by the sweep at the bottom of this file,
# which follows the tree instead of pinning filenames. [st-rfjg, audit row 41]
FIX = "tests/fixtures/schwab_gate"

ALLOW, BLOCK = 0, 2


def run(payload: dict) -> int:
    return subprocess.run(
        ["bash", str(GATE)], input=json.dumps(payload),
        capture_output=True, text=True, cwd=REPO,
    ).returncode


def nested(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def flat(cmd: str) -> dict:
    """The bug shape: command present ONLY at the top level."""
    return {"tool_name": "Bash", "command": cmd}


BLOCKED = [
    ("direct schwab import", f"python3 {FIX}/reaches_schwab_direct.py"),
    ("transitive via broker_schwab", f".venv/bin/python {FIX}/reaches_broker_schwab.py"),
    ("transitive, with args", f".venv/bin/python3 {FIX}/reaches_broker_schwab.py --live"),
    ("inline -c schwab", "python3 -c 'import schwab; print(1)'"),
    ("schwab as module", "python3 -m schwab.something"),
    ("steve's runner", "./scripts/run.sh hello_schwab.py"),
    ("steve's runner, bare", "scripts/run.sh hello_schwab.py"),
    ("token write", "cp /tmp/x tokens/schwab_token.json"),
]

ALLOWED = [
    # A MENTION IS NOT AN INVOCATION. These four are regressions, not hypotheticals:
    # the first cut of gate 3 matched the runner path after any whitespace and
    # blocked this file's own commit message, twice, within minutes of install.
    ("commit message naming the runner",
     'git commit -m "rewrote gate 3 and scripts/run.sh handling"'),
    ("grep for the runner", "grep -rn scripts/run.sh docs/"),
    ("git show of the runner", "git show HEAD:scripts/run.sh"),
    ("ls of the runner", "ls -la scripts/run.sh"),
    ("approved quote reader", ".venv/bin/python3 broker_schwab/readers/quote.py '$SPX'"),
    ("approved chain reader", ".venv/bin/python3 broker_schwab/readers/chain.py '$SPX' --strikes 20"),
    ("pytest", "python3 -m pytest tests/ -q"),
    ("local analysis, no schwab", ".venv/bin/python scripts/level_interaction_read.py --levels 7750"),
    ("liveness shell script", "bash scripts/surface_liveness.sh"),
    ("entitlements probe (tap-in calls this)", ".venv/bin/python3 scripts/entitlements_probe.py"),
    ("git show of a scripts path", "git show HEAD:scripts/run.sh"),
    ("grep mentioning schwab", "grep -rn schwab docs/"),
    ("a .py reaching neither", f".venv/bin/python {FIX}/reaches_nothing.py"),
]


@pytest.mark.parametrize("label,cmd", BLOCKED, ids=[b[0] for b in BLOCKED])
def test_blocks_when_nested(label, cmd):
    assert run(nested(cmd)) == BLOCK, f"{label}: should block, did not"


@pytest.mark.parametrize("label,cmd", BLOCKED, ids=[b[0] for b in BLOCKED])
def test_control_unexpected_shape_fails_closed(label, cmd):
    """THE CONTROL, one turn stronger than COO's version.

    COO's control asserted that a top-level-only payload passes exit 0 against a
    healthy guard — demonstrating that enforcement genuinely depends on correct
    nesting. Correct, but it encodes silent-allow as the expected behaviour, and
    silent-allow on an unrecognised payload is precisely how five gates sat
    dormant from May to August without one symptom.

    So this asserts the fail-CLOSED version: a command present only at the top
    level must BLOCK, with a shape error. Same diagnostic power — if the hook
    regressed to reading the bare key it would evaluate the command normally and
    most of these would return ALLOW, failing here — but the safe direction.

    A first draft of the fix read `.tool_input.command // .command`. This test
    caught it: with a fallback, both shapes are read, nothing proves which one
    is authoritative, and a later regression passes a green suite.
    """
    assert run(flat(cmd)) == BLOCK, (
        f"{label}: top-level-only payload was not refused. Either the hook grew "
        f"a bare-key fallback (which defeats this control) or it silently "
        f"allowed an unrecognised shape. Both are the st-ad6p defect."
    )


@pytest.mark.parametrize("label,cmd", ALLOWED, ids=[a[0] for a in ALLOWED])
def test_allows(label, cmd):
    assert run(nested(cmd)) == ALLOW, f"{label}: should allow, was blocked"


def test_empty_and_malformed_payloads_fail_open_not_crash():
    assert run({}) == ALLOW
    assert run({"tool_input": {}}) == ALLOW
    assert subprocess.run(
        ["bash", str(GATE)], input="not json", capture_output=True, text=True, cwd=REPO
    ).returncode == ALLOW


def test_live_hook_is_the_one_registered_in_settings():
    """The suite must test the gate that actually runs.

    Replaces the pre-install guard that asserted the live hook still had the
    bare-key defect. The failure it protected against is unchanged in spirit: a
    green suite must never be able to mean "the gate is fine" while the gate the
    harness actually invokes is a different, untested file.
    """
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    registered = [
        h["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for h in entry.get("hooks", [])
    ]
    assert str(GATE) in registered, (
        f"{GATE} is not registered as a PreToolUse hook in settings.json — the "
        f"suite is testing a file the harness never runs. Registered: {registered}"
    )


def test_command_is_read_from_the_nested_key():
    """Regression lock on the st-ad6p defect itself.

    Only the COMMAND= assignment is checked. The hook deliberately reads the bare
    `.command` a second time into STRAY, to detect an unrecognised payload shape
    and fail closed — that read is the fail-safe, not the bug, and an earlier
    version of this test wrongly flagged it.
    """
    lines = [
        ln.strip() for ln in GATE.read_text().splitlines()
        if ln.lstrip().startswith("COMMAND=")
    ]
    assert len(lines) == 1, f"expected exactly one COMMAND= assignment, got {lines}"
    assert ".tool_input.command" in lines[0], (
        f"hook reads the bare '.command' key again — this is st-ad6p: {lines[0]}"
    )


def test_the_hook_blocks_when_jq_is_missing(tmp_path):
    """Finding 14, case st-5qjq (approved by Steve 2026-09-01): with jq absent
    from PATH both substitutions yielded empty strings and the hook took its
    allow branch — every gate dormant, no symptom, the May-August shape again.
    The guard fires before anything else needs PATH, so an empty one proves it.
    """
    import os

    empty = tmp_path / "no-tools"
    empty.mkdir()
    proc = subprocess.run(
        ["/bin/bash", str(GATE)],
        input=json.dumps(nested(f"python3 {FIX}/reaches_schwab_direct.py")),
        capture_output=True, text=True, cwd=REPO,
        env={**os.environ, "PATH": str(empty)},
    )
    assert proc.returncode == BLOCK
    assert "jq" in proc.stderr


def test_the_guard_does_not_block_a_healthy_path():
    """The guard must be invisible when jq is present: the same payload that
    blocks above on a jq-less PATH is judged by the gates, not the guard."""
    code = run(nested("ls -la scripts/run.sh"))
    assert code == ALLOW


# --- the live estate, swept ------------------------------------------------
#
# The cases above prove the gate's RULE on fixtures. This proves the rule
# covers the tree as it actually stands today, without naming a single file
# that a prune could remove underneath it. [st-rfjg, audit row 41]

REACHES = re.compile(
    r"^[ \t]*(import[ \t]+(schwab|broker_schwab)|from[ \t]+(schwab|broker_schwab))",
    re.MULTILINE,
)


def _tracked_py() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, text=True
    )
    return [ln for ln in out.stdout.splitlines() if ln]


def _reaching_files() -> list[str]:
    hits = []
    for rel in _tracked_py():
        if rel.startswith("broker_schwab/readers/") or rel.startswith("lib/"):
            continue
        try:
            body = (REPO / rel).read_text(errors="ignore")
        except OSError:
            continue
        if REACHES.search(body):
            hits.append(rel)
    return hits


def test_the_sweep_finds_something_to_check():
    """A sweep that matches nothing would pass silently forever."""
    assert _reaching_files(), (
        "no tracked .py imports schwab or broker_schwab outside the readers — "
        "either the estate changed shape or this sweep's regex broke"
    )


def test_every_reaching_file_in_the_tree_blocks():
    """Every tracked file that reaches the API is refused, readers excepted."""
    allowed = [rel for rel in _reaching_files() if run(nested(f"python3 {rel}")) != BLOCK]
    assert not allowed, f"the gate allowed files that reach the live API: {allowed}"


def test_the_approved_readers_still_pass():
    """The two exemptions are the point of the gate being usable at all."""
    for reader in ("quote.py", "chain.py"):
        cmd = f".venv/bin/python3 broker_schwab/readers/{reader} '$SPX'"
        assert run(nested(cmd)) == ALLOW, f"{reader} must stay reachable"
