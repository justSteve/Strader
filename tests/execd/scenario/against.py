"""Run the scenario suite against the service as it was at another commit. [st-ug1h]

    python3 tests/execd/scenario/against.py <commit> [pytest args...]

e.g. the 09-30 seed cases against the code before each fix::

    python3 tests/execd/scenario/against.py 5ad0386^ tests/execd/scenario/test_seed_0930.py
    python3 tests/execd/scenario/against.py 87ced9c^ tests/execd/scenario/test_seed_0930.py
    python3 tests/execd/scenario/against.py 13e43dd^ tests/execd/scenario/test_seed_0930.py

It copies ``execd/``, ``tests/execd/``, ``tests/conftest.py`` and
``pyproject.toml`` as they were at ``<commit>`` (``git archive``) into a
temporary directory, lays THIS checkout's ``tests/execd/scenario/`` and
``tests/conftest.py`` over them, and runs pytest there. Nothing in the
working tree is touched; the copy is removed afterwards (``--keep`` keeps
it and prints where). The exit status is pytest's.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PATHS = ("execd", "tests/__init__.py", "tests/execd", "tests/conftest.py", "pyproject.toml")


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    argv = [a for a in argv if a != "--keep"]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    commit, args = argv[0], argv[1:] or ["tests/execd/scenario"]
    present = [p for p in PATHS
               if subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{commit}:{p}"],
                                 capture_output=True).returncode == 0]
    tar = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", commit, *present],
                         capture_output=True, check=True).stdout
    root = Path(tempfile.mkdtemp(prefix=f"execd-at-{commit.replace('^', 'p')}-"))
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        tf.extractall(root, filter="data")
    shutil.rmtree(root / "tests/execd/scenario", ignore_errors=True)
    shutil.copytree(REPO / "tests/execd/scenario", root / "tests/execd/scenario",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(REPO / "tests/conftest.py", root / "tests/conftest.py")
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", commit],
                         capture_output=True, text=True).stdout.strip()
    print(f"execd at {commit} ({sha}) with this checkout's scenario suite — {root}", flush=True)
    try:
        return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
                               *args], cwd=root).returncode
    finally:
        if keep:
            print(f"kept {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
