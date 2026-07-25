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

Binary resolution [st-i68]: on this box `az` is the Windows CLI reached through
WSL interop, and it lives on the INTERACTIVE PATH only. Cron's minimal PATH
does not carry it, so the 2026-07-24 06:30 batch died with a bare
``FileNotFoundError: 'az'``. ``resolve_az()`` now searches an explicit order —
``STRADER_AZ_BIN`` env override, then PATH, then known install locations
(including the interop wbin dir) — and raises ``AzCliNotFound`` naming the
binary and every location it looked in. ``AzCliNotFound`` subclasses
``RuntimeError`` on purpose: run.py already treats a RuntimeError from this
module as "keep last-good artifacts", so the clear message lands in the health
alert instead of an unhandled traceback.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ACCOUNT = "stradermailh27ssjitr7spy"
CONTAINER = "mancini"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = REPO_ROOT / "data" / "mancini-letters"

#: Explicit override, checked first. Point it at an az binary when neither PATH
#: nor the fallbacks below are right (a native Linux az, a second WSL install).
AZ_ENV_VAR = "STRADER_AZ_BIN"

#: Searched in order after PATH. First entry is the WSL interop path this box
#: actually uses; the rest cover a native Linux install.
AZ_FALLBACK_PATHS = (
    "/mnt/c/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin/az",
    "/mnt/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az",
    "/usr/bin/az",
    "/usr/local/bin/az",
    "/root/.local/bin/az",
)


class AzCliNotFound(RuntimeError):
    """The Azure CLI could not be located. Carries the search trail."""


def _executable(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def resolve_az() -> str:
    """Return an absolute path to the `az` binary.

    Order: ``STRADER_AZ_BIN`` → PATH → :data:`AZ_FALLBACK_PATHS`.

    Raises :class:`AzCliNotFound` — naming the binary and every location
    searched — instead of letting subprocess raise a bare FileNotFoundError.
    """
    override = (os.environ.get(AZ_ENV_VAR) or "").strip()
    if override:
        if _executable(override):
            return override
        raise AzCliNotFound(
            f"azure CLI not found: {AZ_ENV_VAR}={override!r} is not an executable file. "
            f"Unset {AZ_ENV_VAR} to fall back to PATH, or point it at a real az binary."
        )

    on_path = shutil.which("az")
    if on_path:
        return on_path

    for candidate in AZ_FALLBACK_PATHS:
        if _executable(candidate):
            logger.info("az not on PATH; using fallback %s", candidate)
            return candidate

    searched = "\n  ".join(
        [f"${AZ_ENV_VAR} (unset)",
         f"$PATH ({os.environ.get('PATH', '') or '<empty>'})",
         *AZ_FALLBACK_PATHS]
    )
    raise AzCliNotFound(
        "azure CLI binary 'az' not found — the Mancini letter lives in Azure blob "
        "and cannot be fetched without it.\nSearched:\n  " + searched +
        f"\nFix: set {AZ_ENV_VAR}=/path/to/az, or add the az directory to PATH "
        "(cron runs with a minimal PATH that omits the WSL interop wbin dir)."
    )


def _az(*args: str) -> str:
    az_bin = resolve_az()
    try:
        proc = subprocess.run([az_bin, *args], capture_output=True, text=True)
    except OSError as e:  # resolved but unusable (perms, dead interop shim)
        raise RuntimeError(f"az {' '.join(args[:3])}… could not run ({az_bin}): {e}") from e
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
