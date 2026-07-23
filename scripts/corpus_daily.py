#!/usr/bin/env python3
"""Daily corpus ingestion orchestrator. [co-yva5]

One entry point a scheduler (cron / systemd timer / COO factory wrapper) calls
once per day to keep the corpus fresh enough for the Runbook datastream gate
(runbook/datastream/gate.py, co-i10h). It:

  1. Resolves the target trading day — the most recent *completed* session
     (default: previous weekday; Databento historical is T+1, so "today" has no
     late-day window until after the cash close). Override with --date.
  2. Pulls the two gate-required Databento streams (ES front-month + SPXW OPRA)
     for that day's late-day window, REUSING the verified per-stream scripts
     (scripts/corpus_pull_databento_es.py / corpus_pull_databento.py). Idempotent:
     a stream already present with cycles>0 and no errors is skipped unless
     --force, so a cron retry never double-appends the append-only JSONL.
  3. Optionally attempts the Schwab pull (--include-schwab). Schwab is NOT
     gate-required and its refresh token expires ~weekly; on an OAuth/invalid_grant
     failure the orchestrator raises a SPECIFIC, actionable alert ("run
     scripts/refresh_schwab_token.py") instead of letting the error rot silently
     in the manifest.
  4. Evaluates corpus health via gate.evaluate (single source of truth) and
     ALERTS on any unhealthy required stream (missing / empty / errored / stale).
  5. Emits a structured health record to the corpus health log and exits non-zero
     when unhealthy, so the calling scheduler surfaces the failure.

Cost (2026-07-01 estimate): ES GLBX ~$0.11 / 2h window (metered); OPRA flat-fee
($0.00 incremental under the current subscription). ~$0.11/day, ~$27/yr.

Usage:
    .venv/bin/python scripts/corpus_daily.py                 # most recent weekday
    .venv/bin/python scripts/corpus_daily.py --date 2026-06-30
    .venv/bin/python scripts/corpus_daily.py --include-schwab
    .venv/bin/python scripts/corpus_daily.py --dry-run       # resolve+plan only, no spend
    .venv/bin/python scripts/corpus_daily.py --json          # machine-readable health

Exit codes:
    0  all required streams healthy
    1  one or more required streams unhealthy (alert emitted)
    2  a pull subprocess failed to run (infrastructure error)
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import date as _date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.corpus.paths import (  # noqa: E402
    CORPUS_ROOT,
    manifest_path,
    most_recent_session_day,
)
from runbook.datastream import gate  # noqa: E402

logger = logging.getLogger("corpus_daily")

# Health-log: append-only audit trail of every orchestrator run, next to the
# corpus. A stale/errored run leaves a durable record an operator can inspect.
HEALTH_LOG = CORPUS_ROOT / "_health.jsonl"

# The gate-required Databento streams and the script that pulls each.
DATABENTO_PULLS = {
    "databento_glbx_es": "corpus_pull_databento_es.py",
    "databento_opra": "corpus_pull_databento.py",
}

# Per-stream CT pull windows. ES trades cover the full cash session for the
# orderflow layer (st-f05; ~$0.60/day metered GLBX approved 2026-07-04). OPRA
# stays late-day: flat-fee, but full-RTH option ticks would ~3x storage with
# no consumer — the butterfly corpus only needs the final two hours.
STREAM_WINDOWS = {
    "databento_glbx_es": ("08:30", "15:00"),
    "databento_opra": ("13:00", "15:00"),
}
SCHWAB_PULL = "corpus_pull_schwab.py"
# Proactive Schwab token-age heartbeat (st-e2f). Runs every day regardless of
# --include-schwab: the whole point is to warn BEFORE the 7-day refresh wall even
# on days we don't pull Schwab. It owns its own alert/heartbeat/bead surfaces and
# is deliberately isolated from the datastream gate — Schwab is not gate-required,
# so an aging token must NOT mark the (Databento) corpus unhealthy.
SCHWAB_TOKEN_HEALTH = "schwab_token_health.py"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_target_day(explicit: str | None) -> _date:
    """Most recent completed session. Default: previous weekday (walks back over
    Sat/Sun) via market.corpus.paths.most_recent_session_day — the shared helper
    the datastream gate also uses, so ingestion and gate target the same day.
    Holidays are NOT modeled — a holiday yields a 0-tick pull that the health
    check flags, which is the safe failure (an alert, not silent bad data).
    """
    if explicit:
        return _date.fromisoformat(explicit)
    return most_recent_session_day()


def stream_healthy_in_manifest(day: _date, stream: str) -> bool:
    """True if the day's manifest already records this stream with cycles>0 and
    no errors — the idempotency guard against re-pulling on a cron retry."""
    path = manifest_path(day)
    if not path.exists():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    st = (manifest.get("streams") or {}).get(stream)
    if not st:
        return False
    return (st.get("cycles", 0) or 0) > 0 and not (st.get("errors") or [])


def run_pull(script: str, day: _date, extra: list[str] | None = None) -> tuple[int, str]:
    """Invoke a per-stream pull script in this interpreter's venv. Returns
    (returncode, combined_output). Never raises on non-zero — the caller decides."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / script), "--date", day.isoformat()]
    if extra:
        cmd += extra
    logger.info("pull: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        logger.error("pull FAILED (%s exit=%s):\n%s", script, proc.returncode, out.strip())
    return proc.returncode, out


def run_token_health() -> int:
    """Fire the proactive Schwab token-age heartbeat (st-e2f) as a subprocess,
    matching the run_pull convention. Date-independent and free (local file read),
    so it runs on every corpus_daily invocation — including --dry-run. Returns the
    checker's rc (0 ok, 1 action-needed, 2 internal) for logging only; the caller
    does NOT fold it into the datastream gate exit code."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / SCHWAB_TOKEN_HEALTH)]
    logger.info("token-health: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        logger.info("schwab token healthy")
    else:
        logger.warning("schwab token heartbeat rc=%s:\n%s", proc.returncode, out.strip())
    return proc.returncode


def _is_schwab_auth_failure(manifest_day: _date) -> bool:
    """Detect the recurring Schwab refresh-token-expiry signature in the manifest."""
    path = manifest_path(manifest_day)
    if not path.exists():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    errs = " ".join((manifest.get("streams", {}).get("schwab", {}) or {}).get("errors", []))
    return "invalid_grant" in errs or "Refresh token" in errs


def emit_alert(kind: str, message: str, detail: dict) -> None:
    """Surface an actionable alert. Transport-pluggable: today it writes a durable
    line to the corpus health log and a loud stderr banner (both captured by any
    cron wrapper). Operator-push transports (relay/ClaudeClaw, a bd bead) are a
    documented seam — wire them once co-yva5's ownership/routing is decided."""
    record = {"ts": _utc_now_iso(), "level": "alert", "kind": kind,
              "message": message, **detail}
    _append_health(record)
    banner = f"\n{'!' * 72}\nCORPUS ALERT [{kind}]: {message}\n{'!' * 72}"
    print(banner, file=sys.stderr)
    logger.error("ALERT [%s]: %s", kind, message)


def _append_health(record: dict) -> None:
    HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with HEALTH_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Daily corpus ingestion orchestrator [co-yva5]")
    ap.add_argument("--date", help="Target trading day YYYY-MM-DD (default: most recent weekday)")
    ap.add_argument("--force", action="store_true",
                    help="Re-pull even if a stream is already healthy (WARNING: append-only, double-counts)")
    ap.add_argument("--include-schwab", action="store_true",
                    help="Also attempt the Schwab pull (not gate-required; may need re-auth)")
    ap.add_argument("--start-ct", default=None,
                    help="Window start CT for ALL streams (default: per-stream STREAM_WINDOWS)")
    ap.add_argument("--end-ct", default=None,
                    help="Window end CT for ALL streams (default: per-stream STREAM_WINDOWS)")
    ap.add_argument("--max-age-hours", type=float, default=gate.DEFAULT_MAX_AGE_HOURS,
                    help=f"Staleness threshold for the health check (default {gate.DEFAULT_MAX_AGE_HOURS})")
    ap.add_argument("--dry-run", action="store_true", help="Resolve + plan only; no pulls, no spend")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable health JSON to stdout")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    day = resolve_target_day(args.date)
    logger.info("corpus_daily target day = %s", day)

    # Proactive Schwab token-age heartbeat (st-e2f) — runs unconditionally, owns
    # its own alerting, and never affects the datastream gate exit code below.
    run_token_health()

    pull_failed = False

    # --- Databento (gate-required) --------------------------------------------
    for stream, script in DATABENTO_PULLS.items():
        default_start, default_end = STREAM_WINDOWS[stream]
        window = ["--start-ct", args.start_ct or default_start,
                  "--end-ct", args.end_ct or default_end]
        if not args.force and stream_healthy_in_manifest(day, stream):
            logger.info("skip %s: already healthy in manifest for %s", stream, day)
            continue
        if args.dry_run:
            logger.info("[dry-run] would pull %s via %s (window %s-%s CT)",
                        stream, script, window[1], window[3])
            continue
        logger.info("%s window %s-%s CT", stream, window[1], window[3])
        rc, _ = run_pull(script, day, window)
        if rc != 0:
            pull_failed = True

    # --- Internals snapshot (not gate-required) [st-3fr] ----------------------
    # Schwab minute history for $TICK/$TRIN/$ADD/$VOLD is a rolling ~47-day
    # window; a daily full-range refresh (4 API calls total, no metering)
    # makes the history permanent AND heals the same-day clamped segments
    # (negatives floored at 0 until T+1 — see internals-tick-seed doc).
    # --force on the last 3 days rewrites the healed data over stale copies.
    # (range-shaped script — no --date, so it bypasses run_pull's injection)
    if not args.dry_run:
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "corpus_pull_internals.py"),
               "--days", "45", "--force"]
        logger.info("pull: %s", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            logger.warning("internals snapshot failed rc=%s (not gate-blocking):\n%s",
                           proc.returncode,
                           ((proc.stdout or "") + (proc.stderr or "")).strip())
    else:
        logger.info("[dry-run] would refresh internals snapshot (45d, force)")

    # --- Mancini morning parse (not gate-required) [st-ze6] -------------------
    # Pre-open chain: fetch newest letter blob -> parse (hybrid deterministic
    # levels if the interpretive leg is credit-blocked) -> validate -> persist
    # + brief. Runs its own datastream gate internally. Failure alerts but
    # never blocks the corpus fill.
    if not args.dry_run:
        cmd = [sys.executable, "-m", "runbook.mancini.run", "--from-blob"]
        logger.info("mancini: %s", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            emit_alert(
                "mancini_parse",
                f"Morning Mancini parse failed (rc={proc.returncode}) — "
                "last-good artifacts still stand; run manually or in-session.",
                {"returncode": proc.returncode,
                 "tail": ((proc.stdout or "") + (proc.stderr or ""))[-500:]},
            )
    else:
        logger.info("[dry-run] would run Mancini morning parse (--from-blob)")

    # --- Schwab (optional, not gate-required) ---------------------------------
    if args.include_schwab and not args.dry_run:
        rc, out = run_pull(SCHWAB_PULL, day)
        if rc != 0 or _is_schwab_auth_failure(day):
            emit_alert(
                "schwab_reauth",
                "Schwab pull failed — refresh token expired/revoked. "
                "Steve must run: python scripts/refresh_schwab_token.py (interactive browser OAuth).",
                {"day": day.isoformat(), "returncode": rc},
            )
    elif args.include_schwab and args.dry_run:
        logger.info("[dry-run] would attempt Schwab pull")

    # --- Health evaluation (single source of truth: gate.evaluate) ------------
    if args.dry_run:
        logger.info("[dry-run] complete — no pulls executed")
        return 0

    result = gate.check(day=day, max_age_hours=args.max_age_hours)
    health = {"ts": _utc_now_iso(), "day": day.isoformat(),
              "ok": result.ok, "reasons": result.reasons, "checked": result.checked}
    _append_health({"level": "run", **health})

    if args.json:
        print(json.dumps(health, indent=2))
    else:
        status = "HEALTHY" if result.ok else "UNHEALTHY"
        print(f"corpus {day} datastream: {status}")
        for name, info in result.checked.items():
            print(f"  {name}: {info}")
        for r in result.reasons:
            print(f"  reason: {r}")

    if not result.ok:
        emit_alert("datastream_unhealthy",
                   f"Datastream gate FAILED for {day}: {'; '.join(result.reasons)}",
                   {"day": day.isoformat(), "reasons": result.reasons})
        return 1
    if pull_failed:
        # Streams are healthy overall but at least one pull subprocess errored.
        return 2

    logger.info("corpus %s healthy — all required streams fresh", day)
    return 0


if __name__ == "__main__":
    sys.exit(main())
