"""Azure blob fetch for the Mancini letter — the codified manual link. [st-ze6]

Wraps the enterprise email-ingress container (COO's ingress pipeline lands
Mancini's Substack mail here as YYYY-MM-DD-HHMMSS.txt blobs). This module
lifts the proven az-CLI pattern from scripts/session_review.py so run.py can
fetch the newest letter directly (``--from-blob``) instead of a human piping
it in. Downloads cache under data/mancini-letters/ (gitignored) — repeat runs
never re-hit Azure.

Auth: az CLI storage-key lookup — the caller's `az login` must be able to
read the account. COO's co-51rk heartbeat asserts blob *landing* upstream;
this module only reads.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ACCOUNT = "stradermailh27ssjitr7spy"
CONTAINER = "mancini"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = REPO_ROOT / "data" / "mancini-letters"


def _az(*args: str) -> str:
    proc = subprocess.run(["az", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"az {' '.join(args[:3])}… failed: {proc.stderr.strip()[:300]}")
    # WSL az emits trailing CRs on tsv output; an un-stripped blob name 400s
    return proc.stdout.replace("\r", "")


def fetch_latest() -> tuple[str, str]:
    """Download (or serve from cache) the newest letter blob.

    Returns (blob_name, raw_text). Raises RuntimeError when the container is
    unreachable or empty — the caller decides whether that halts the run.
    """
    key = _az("storage", "account", "keys", "list", "--account-name", ACCOUNT,
              "--query", "[0].value", "-o", "tsv", "--only-show-errors").strip()
    out = _az("storage", "blob", "list", "--account-name", ACCOUNT,
              "--account-key", key, "--container-name", CONTAINER,
              "--query", "[].name", "-o", "tsv")
    names = sorted(n for n in out.split() if n.endswith(".txt"))
    if not names:
        raise RuntimeError(f"no letter blobs in {ACCOUNT}/{CONTAINER}")
    newest = names[-1]
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / newest
    if not path.exists():
        _az("storage", "blob", "download", "--account-name", ACCOUNT,
            "--account-key", key, "--container-name", CONTAINER,
            "--name", newest, "--file", str(path), "--no-progress", "-o", "none")
        logger.info("downloaded %s (%.0f KB)", newest, path.stat().st_size / 1024)
    else:
        logger.info("cache hit: %s", newest)
    return newest, path.read_text(encoding="utf-8", errors="replace")
