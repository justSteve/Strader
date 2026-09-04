#!/usr/bin/env python3
"""Daily corpus ingestion orchestrator. [co-yva5]

One entry point a scheduler (cron / systemd timer / COO factory wrapper) calls
once per day to keep the corpus fresh enough for the Runbook datastream gate
(runbook/datastream/gate.py, co-i10h). It:

  1. Resolves the target trading day — the most recent *completed* session
     (default: previous weekday; Databento historical is T+1, so "today" has no
     late-day window until after the cash close). Override with --date.
  2. Pulls the gate-required Databento stream (ES front-month; the SPXW OPRA
     pull was DROPPED from the nightly on Steve's "drop", 2026-08-17 — no live
     OPRA entitlement since the ~08-04 plan swap, and the nightly attempt had
     exited rc=2 for five sessions; historical OPRA stays ad hoc via
     corpus_pull_databento.py) for that day's window, REUSING the verified
     per-stream script (scripts/corpus_pull_databento_es.py). Idempotent:
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

Cost: ES GLBX historical is flat-rate under the held CME/Futures plan (measured
$0.0000 for a session day, 2026-08-05); OPRA is not pulled nightly.

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
from market.corpus.writer import update_manifest  # noqa: E402
from runbook.datastream import gate  # noqa: E402
from strader import entitlements  # noqa: E402

logger = logging.getLogger("corpus_daily")

# Health-log: append-only audit trail of every orchestrator run, next to the
# corpus. A stale/errored run leaves a durable record an operator can inspect.
HEALTH_LOG = CORPUS_ROOT / "_health.jsonl"

# The gate-required Databento streams and the script that pulls each.
# "databento_opra": "corpus_pull_databento.py" was removed 2026-08-17 (Steve:
# "drop", COO session 246c8647; bead co-03ojd.14) — the gate had already stopped
# requiring it on 2026-08-07 (runbook/datastream/gate.py), but this dict kept
# trying the pull, it failed without an entitlement, and the run exited rc=2
# every night. Re-add the pair here to restore a nightly OPRA pull.
DATABENTO_PULLS = {
    "databento_glbx_es": "corpus_pull_databento_es.py",
}

# Per-stream CT pull windows. ES trades cover the full cash session for the
# orderflow layer (st-f05). The OPRA window ("13:00", "15:00") is kept for the
# ad-hoc pull path even though the nightly no longer runs it.
STREAM_WINDOWS = {
    "databento_glbx_es": ("08:30", "15:00"),
    "databento_opra": ("13:00", "15:00"),
}
# MBP-1 backfill authorization is derived from the entitlements registry at run
# time, not from a date list (st-xxo0; supersedes the st-ve6 July pre-approval).
# While the registry's dated `databento_plan` entry says the CME/Futures plan
# (GLBX.MDP3) is held live, a historical GLBX pull is flat-rate — measured
# $0.0000 for a full session day (2026-08-05, --estimate-only) — so the per-day
# spend approval the old date list encoded has nothing to approve. If the
# registry ever stops saying `active`, a pull is usage-billed again and this
# refuses, saying why, until Steve rules. A missing or unparseable registry also
# refuses: fail closed, never guess an entitlement.
# Not gate-required: a failed MBP-1 pull warns but never fails the datastream gate.
MBP1_STREAM = "databento_glbx_es_mbp1"
MBP1_SCRIPT = "corpus_pull_databento_es_mbp1.py"
MBP1_PLAN_ID = "databento_plan"


def mbp1_authorization(registry_path: str | None = None) -> tuple[bool, str]:
    """(authorized, reason) for an MBP-1 backfill, per the entitlements registry."""
    try:
        state = entitlements.dated_state(MBP1_PLAN_ID, registry_path)
    except Exception as exc:  # noqa: BLE001 — any load failure means "cannot verify"
        return False, (f"entitlements registry unreadable ({exc}) — refusing "
                       "MBP-1 backfill rather than guessing the plan state")
    if state == "active":
        return True, ("GLBX.MDP3 held live (registry: databento_plan=active) — "
                      "historical GLBX is flat-rate, no per-pull spend")
    return False, (f"GLBX plan not held live (registry: databento_plan={state!r}) — "
                   "a historical MBP-1 pull would be usage-billed; needs Steve's spend ruling")


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
    st = _stream_state(day, stream)
    return bool(st) and (st.get("cycles", 0) or 0) > 0 and not (st.get("errors") or [])


def stream_has_rows_in_manifest(day: _date, stream: str) -> tuple[bool, list[str]]:
    """(True, errors) when the manifest records this stream with cycles>0 —
    healthy or not. [st-n0qm, Watcher V2 plan Risk 15]

    A stream that captured rows live is not a MISSING stream: appending the
    whole session batch onto it writes a second copy of every print, and the
    prior-day profile seed (Phase 2) then reads a doubled tape. Measured
    2026-08-11: the live capture recorded a normal reconnect note in `errors`,
    the healthy-check said "unhealthy", the batch appended 08:30-15:00 CT and
    the day closed at 496,011 cycles against ~260k on its neighbours. A
    reconnect is a gap, and a gap wants a windowed pull — never a full-session
    append. `--force` remains the way to do that on purpose.
    """
    st = _stream_state(day, stream)
    if not st:
        return False, []
    return (st.get("cycles", 0) or 0) > 0, list(st.get("errors") or [])


def _stream_state(day: _date, stream: str) -> dict | None:
    path = manifest_path(day)
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    st = (manifest.get("streams") or {}).get(stream)
    return st if isinstance(st, dict) else None


def resolve_transport_notes(day: _date, stream: str) -> int:
    """After a batch pull has replaced a stream's rows from the history host,
    the live capture's reconnect notes on that stream describe a transport
    that is no longer the source of the rows. Move them into the manifest's
    ``errors_resolved`` record so the day reads clean and the compactor packs
    it; the count and a sample stay. Returns the number resolved. Only
    reconnect-shaped notes are resolved — a real error stays where it is.
    [co-8b60y]"""
    st = _stream_state(day, stream) or {}
    errs = list(st.get("errors") or [])
    dropped = int(st.get("errors_dropped", 0) or 0)
    if not errs and not dropped:
        return 0
    if not all(gate._is_reconnect_error(e) for e in errs):
        logger.warning("%s: %d error(s) on %s are not all reconnect notes — left in place",
                       stream, len(errs), day)
        return 0
    total = len(errs) + dropped
    update_manifest(day, stream, resolve_errors=True,
                    note=f"batch pull complete; {total} live-capture reconnect note(s) resolved")
    logger.info("%s: %d reconnect note(s) resolved for %s after the batch pull",
                stream, total, day)
    return total


def run_pull(script: str, day: _date, extra: list[str] | None = None,
             pass_date: bool = True) -> tuple[int, str]:
    """Invoke a per-stream pull script in this interpreter's venv. Returns
    (returncode, combined_output). Never raises on non-zero — the caller decides.

    pass_date=False is for snapshot scripts (corpus_pull_schwab.py) that write
    to TODAY's day-dir and take no --date; injecting one made the pull die on
    argparse before it ever reached the API, which is why --include-schwab
    could never have restored the stream [st-096].
    """
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / script)]
    if pass_date:
        cmd += ["--date", day.isoformat()]
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
        if not args.force:
            has_rows, errs = stream_has_rows_in_manifest(day, stream)
            if has_rows:
                # Rows exist (live capture) but the stream carries error notes.
                # Do NOT append the session batch on top of a live tape [Risk 15];
                # say what the errors were so a real gap gets a windowed pull.
                logger.warning("skip %s: %s already holds rows for %s (errors: %s) — "
                               "a batch append would double the tape; use --force with "
                               "--start-ct/--end-ct to fill a specific gap",
                               stream, stream, day, "; ".join(errs) or "-")
                continue
        if args.dry_run:
            logger.info("[dry-run] would pull %s via %s (window %s-%s CT)",
                        stream, script, window[1], window[3])
            continue
        logger.info("%s window %s-%s CT", stream, window[1], window[3])
        rc, _ = run_pull(script, day, window)
        if rc != 0:
            pull_failed = True
        else:
            resolve_transport_notes(day, stream)

    # --- MBP-1 (registry-authorized, not gate-required) [st-xxo0] -------------
    mbp1_ok, mbp1_reason = mbp1_authorization()
    if not mbp1_ok:
        logger.warning("MBP-1 backfill refused for %s: %s", day, mbp1_reason)
    elif not args.force and stream_healthy_in_manifest(day, MBP1_STREAM):
        logger.info("skip %s: already healthy in manifest for %s", MBP1_STREAM, day)
    elif not args.force and stream_has_rows_in_manifest(day, MBP1_STREAM)[0]:
        # Risk 15 again, on the depth stream this time. The trades loop above
        # got this guard after 2026-08-11; MBP-1 kept the healthy-only check and
        # doubled 2026-08-19 on 2026-08-20 — 12,377,582 cycles against a 6.25M
        # median (max on any other day 9.92M), the appended batch visible at the
        # file tail: last record ts_event 14:59:59.999 CT (the --end-ct bound)
        # with batch provenance (ES.c.0, no "source": "live"), while the live
        # capture ran to 18:46. A stream carrying reconnect notes is not a
        # missing stream; a gap wants a windowed --force pull, never a
        # full-session append. [co-j5qzq]
        _, errs = stream_has_rows_in_manifest(day, MBP1_STREAM)
        logger.warning("skip %s: already holds rows for %s (errors: %s) — "
                       "a batch append would double the depth tape; use --force "
                       "with --start-ct/--end-ct to fill a specific gap",
                       MBP1_STREAM, day, "; ".join(errs) or "-")
        emit_alert(
            "mbp1_errors",
            f"MBP-1 depth for {day} carries {len(errs)} reconnect note(s) — rows "
            f"are present and were NOT re-pulled (a batch append would double "
            f"the tape). Verify coverage before filling: "
            f".venv/bin/python scripts/{MBP1_SCRIPT} --date {day.isoformat()} "
            f"--force --start-ct HH:MM --end-ct HH:MM",
            {"day": day.isoformat(), "errors": errs},
        )
    elif args.dry_run:
        logger.info("[dry-run] would pull %s (%s)", MBP1_STREAM, mbp1_reason)
    else:
        logger.info("%s: %s", MBP1_STREAM, mbp1_reason)
        rc, _ = run_pull(MBP1_SCRIPT, day,
                         ["--start-ct", "08:30", "--end-ct", "15:00"])
        if rc == 0 and stream_has_rows_in_manifest(day, MBP1_STREAM)[0]:
            resolve_transport_notes(day, MBP1_STREAM)
        if rc != 0 or not stream_has_rows_in_manifest(day, MBP1_STREAM)[0]:
            # No rows from either source. Live capture is the only other source
            # of MBP-1 depth, so a day with no rows after the backfill attempt is
            # a durable gap and alerts rather than rotting as a log line.
            # Non-gate-blocking. Note this tests for ROWS, not health: a stream
            # that captured rows with reconnect notes is not missing depth.
            emit_alert(
                "mbp1_gap",
                f"MBP-1 depth missing for {day} after backfill attempt "
                f"(rc={rc}) — re-run manually: "
                f".venv/bin/python scripts/{MBP1_SCRIPT} --date {day.isoformat()}",
                {"day": day.isoformat(), "returncode": rc},
            )

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

    # --- Mancini morning parse — MOVED OUT of this chain [st-q1n] -------------
    # Until 2026-07-30 the parse ran here, inline, which tied it to this batch's
    # 06:30 CT slot. The two jobs want opposite clocks: the Databento T+1 pull
    # runs as early as the vendor has data, while the Mancini plan wants to run
    # as LATE as possible so its overnight interaction brief (st-doz) measures
    # the most ETH price action against the day's levels. It now has its own
    # cron at 08:15 CT — scripts/cron/mancini-preopen-wrapper.sh.
    #
    # The ordering this batch provided is preserved, not lost: corpus_daily
    # still fills data/corpus/<day>/ at 06:30, so run.py's datastream gate
    # passes when the parse fires two hours later. If this batch is ever moved
    # later than 08:15, the parse starts failing its gate — move the parse too.

    # --- Schwab (optional, not gate-required) ---------------------------------
    # Snapshot lands in TODAY's day-dir, not the T+1 target day: a live quote
    # pulled this morning is this morning's data. The daily stage cadence is
    # owned by scripts/cron/schwab-stages-wrapper.sh [st-096]; this flag is the
    # batch-run escape hatch.
    if args.include_schwab and not args.dry_run:
        rc, out = run_pull(SCHWAB_PULL, day, ["--stage", "daily-batch"],
                           pass_date=False)
        if rc != 0 or _is_schwab_auth_failure(_date.today()):
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
              "ok": result.ok, "status": result.status,
              "reasons": result.reasons, "warnings": result.warnings,
              "checked": result.checked}
    _append_health({"level": "run", **health})

    if args.json:
        print(json.dumps(health, indent=2))
    else:
        print(f"corpus {day} datastream: {result.status}")
        for name, info in result.checked.items():
            print(f"  {name}: {info}")
        for r in result.reasons:
            print(f"  reason: {r}")
        for w in result.warnings:
            print(f"  degraded: {w}")

    if not result.ok:
        emit_alert("datastream_unhealthy",
                   f"Datastream gate FAILED for {day}: {'; '.join(result.reasons)}",
                   {"day": day.isoformat(), "reasons": result.reasons})
        return 1
    if result.degraded:
        # The required tape is fine, so the day proceeds — but a configured
        # stream ran and got nothing, and that used to vanish into the
        # manifest. One durable alert per run. [co-03ojd.7 J-F3]
        emit_alert("datastream_degraded",
                   f"Datastream DEGRADED for {day}: {'; '.join(result.warnings)}",
                   {"day": day.isoformat(), "warnings": result.warnings})
    if pull_failed:
        # Streams are healthy overall but at least one pull subprocess errored.
        return 2

    logger.info("corpus %s healthy — all required streams fresh", day)
    return 0


if __name__ == "__main__":
    sys.exit(main())
