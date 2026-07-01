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
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.corpus.paths import CORPUS_ROOT, central_date, manifest_path  # noqa: E402
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
SCHWAB_PULL = "corpus_pull_schwab.py"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_target_day(explicit: str | None) -> _date:
    """Most recent completed session. Default: previous weekday (walks back over
    Sat/Sun). Holidays are NOT modeled — a holiday yields a 0-tick pull that the
    health check flags, which is the safe failure (an alert, not silent bad data).
    """
    if explicit:
        return _date.fromisoformat(explicit)
    d = central_date() - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


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
    ap.add_argument("--start-ct", default="13:00", help="Late-day window start CT (default 13:00)")
    ap.add_argument("--end-ct", default="15:00", help="Late-day window end CT (default 15:00)")
    ap.add_argument("--max-age-hours", type=float, default=gate.DEFAULT_MAX_AGE_HOURS,
                    help=f"Staleness threshold for the health check (default {gate.DEFAULT_MAX_AGE_HOURS})")
    ap.add_argument("--dry-run", action="store_true", help="Resolve + plan only; no pulls, no spend")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable health JSON to stdout")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    day = resolve_target_day(args.date)
    window = ["--start-ct", args.start_ct, "--end-ct", args.end_ct]
    logger.info("corpus_daily target day = %s (window %s-%s CT)", day, args.start_ct, args.end_ct)

    pull_failed = False

    # --- Databento (gate-required) --------------------------------------------
    for stream, script in DATABENTO_PULLS.items():
        if not args.force and stream_healthy_in_manifest(day, stream):
            logger.info("skip %s: already healthy in manifest for %s", stream, day)
            continue
        if args.dry_run:
            logger.info("[dry-run] would pull %s via %s", stream, script)
            continue
        rc, _ = run_pull(script, day, window)
        if rc != 0:
            pull_failed = True

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
