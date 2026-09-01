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
from typing import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

ACCOUNT = "stradermailh27ssjitr7spy"
CONTAINER = "mancini"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = REPO_ROOT / "data" / "mancini-letters"

#: How far back from the newest blob to look for an actual letter. The
#: container is an email ingress, so receipts and announcements land in it too
#: (st-znw6). Bounded so a container full of non-letters cannot walk — and
#: download — the whole history looking for one.
MAX_CANDIDATES = 8

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


def is_letter(raw: str) -> tuple[bool, str]:
    """Does this blob's text actually contain a trade plan? [st-znw6]

    Returns (verdict, reason). The test is the one the pipeline already
    computes: clean the text and ask ``segment()`` whether it found the level
    ladder. ``anchored`` is exactly "this reads like a Mancini letter", so the
    check costs nothing new and cannot disagree with the parse that follows.

    Deliberately NOT a filename pattern and NOT a size threshold. Both are
    guesses about a format we do not control — Substack decides what lands in
    that container, and the day it changes its receipt template a size rule
    fails silently while this one keeps working.

    Imported lazily so a caller that only wants ``resolve_az`` does not pay for
    the HTML parser, and so this module keeps no import-time dependency on the
    rest of the package.
    """
    from runbook.mancini.clean import clean_newsletter
    from runbook.mancini.segment import segment

    try:
        seg = segment(clean_newsletter(raw))
    except Exception as exc:  # noqa: BLE001 — an unparseable blob is not a letter
        return False, f"clean/segment raised {type(exc).__name__}: {exc}"
    if not seg.anchored:
        return False, f"no level ladder found (anchored=False, {seg.source_len} clean chars)"
    if seg.missing:
        # Anchored but incomplete: still a letter, still parseable. Say so and
        # let it through — the parse reports missing sections itself, and
        # refusing here would silently prefer an older complete letter over
        # today's partial one, which is the wrong trade on a plan-day.
        logger.warning("%s is anchored but missing sections: %s",
                       "candidate", ", ".join(seg.missing))
    return True, f"anchored, {seg.source_len} clean chars, {len(seg.forward_text)} forward"


def _download(name: str, key: str) -> Path:
    """Fetch one blob into the cache, or serve it from there."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        _az("storage", "blob", "download", "--account-name", ACCOUNT,
            "--account-key", key, "--container-name", CONTAINER,
            "--name", name, "--file", str(path), "--no-progress", "-o", "none")
        logger.info("downloaded %s (%.0f KB)", name, path.stat().st_size / 1024)
    else:
        logger.info("cache hit: %s", name)
    return path


def select_letter(names: list[str], read: "Callable[[str], str]",
                  max_attempts: int = MAX_CANDIDATES) -> tuple[str, str]:
    """Newest-first, return the first blob that is actually a letter. [st-znw6]

    ``read`` takes a blob name and returns its raw text — injected so the
    selection logic is testable without Azure, which is the whole reason this
    is a separate function.

    Why this exists: the container is an email ingress, not a letter store, so
    anything Substack sends lands in it. On 2026-09-01 a subscription RECEIPT
    arrived as ``2026-09-01-065032.txt`` and sorted after Monday evening's real
    letter — 683 clean chars, no ladder. The old ``names[-1]`` would have run
    the morning parse against a billing email and produced nothing.

    Every skip is logged with its reason. A silent skip is how this class of
    bug hides, and this one hid until a receipt happened to arrive on a
    plan-day.
    """
    tried: list[str] = []
    for name in reversed(names[-max_attempts:]):
        raw = read(name)
        ok, reason = is_letter(raw)
        if ok:
            if tried:
                logger.warning("skipped %d non-letter blob(s) before %s: %s",
                               len(tried), name, "; ".join(tried))
            logger.info("selected %s (%s)", name, reason)
            return name, raw
        tried.append(f"{name} ({reason})")
        logger.warning("skipping %s — %s", name, reason)
    raise RuntimeError(
        f"no letter among the newest {min(max_attempts, len(names))} blobs in "
        f"{ACCOUNT}/{CONTAINER}: {'; '.join(tried)}"
    )


def fetch_latest() -> tuple[str, str]:
    """Download (or serve from cache) the newest blob that is actually a letter.

    Returns (blob_name, raw_text) — text stays RAW so the caller's clean and
    segment steps are unchanged. Raises RuntimeError when the container is
    unreachable, empty, or holds no letter in its newest
    ``MAX_CANDIDATES`` blobs.
    """
    key = _az("storage", "account", "keys", "list", "--account-name", ACCOUNT,
              "--query", "[0].value", "-o", "tsv", "--only-show-errors").strip()
    out = _az("storage", "blob", "list", "--account-name", ACCOUNT,
              "--account-key", key, "--container-name", CONTAINER,
              "--query", "[].name", "-o", "tsv")
    names = sorted(n for n in out.split() if n.endswith(".txt"))
    if not names:
        raise RuntimeError(f"no letter blobs in {ACCOUNT}/{CONTAINER}")

    def read(name: str) -> str:
        return _download(name, key).read_text(encoding="utf-8", errors="replace")

    return select_letter(names, read)
