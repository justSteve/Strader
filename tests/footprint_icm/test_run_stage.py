"""run_stage.sh's guards, without a model call. [st-h0xx]

The isolation claim is "no project instructions, no auto-memory, no tools,
no settings" — the first two are this script's to check before it calls
anything, so they are tested here by building the folders it must refuse.
"""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "footprint-icm/bin/run_stage.sh"


def run(stage: Path, *args, home: Path):
    env = {**os.environ, "HOME": str(home), "PATH": "/usr/bin:/bin"}
    return subprocess.run(["bash", str(SCRIPT), str(stage), *args], capture_output=True,
                          text=True, env=env, timeout=60)


def test_refuses_a_stage_with_project_instructions_in_a_parent(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# rules\n")
    stage = tmp_path / "run" / "20-classify"
    stage.mkdir(parents=True)
    r = run(stage, "--smoke", home=tmp_path / "home")
    assert r.returncode == 2
    assert "project instructions reachable" in r.stderr and "CLAUDE.md" in r.stderr


def test_refuses_a_stage_with_auto_memory_for_its_folder(tmp_path):
    stage = tmp_path / "run" / "20-classify"
    stage.mkdir(parents=True)
    home = tmp_path / "home"
    key = str(stage.resolve()).replace("/", "-")
    (home / ".claude/projects" / key / "memory").mkdir(parents=True)
    r = run(stage, "--smoke", home=home)
    assert r.returncode == 2
    assert "auto-memory exists" in r.stderr


def test_refuses_a_stage_without_prompt_and_input(tmp_path):
    stage = tmp_path / "run" / "20-classify"
    stage.mkdir(parents=True)
    r = run(stage, home=tmp_path / "home")
    assert r.returncode == 2 and "no prompt.md" in r.stderr
    (stage / "prompt.md").write_text("p")
    r = run(stage, home=tmp_path / "home")
    assert r.returncode == 2 and "no input.txt" in r.stderr
