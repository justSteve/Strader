#!/usr/bin/env bash
# mancini-preopen-wrapper.sh — Fire the Mancini plan parse close to the open. [st-q1n]
#
#   15 8 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/mancini-preopen-wrapper.sh
#
# WHY THIS EXISTS AS ITS OWN CRON. Until 2026-07-30 the parse was a step inside
# scripts/corpus_daily.py, so it rode COO's 06:30 CT corpus-daily-wrapper.sh.
# Two different jobs were sharing one clock. The Databento T+1 batch pull wants
# to run as early as the vendor has data; the Mancini parse wants to run as LATE
# as possible, because the plan doc carries an overnight interaction brief
# (st-doz) built at parse time from ES 5-minute ETH bars. Every minute of delay
# is another minute of overnight price action measured against the day's levels.
#
# 08:15 CT (Steve, 2026-07-30) captures ~15h15m of the ~15h30m overnight session
# — the ETH session opens 17:00 CT the prior day and the cash open is 08:30 CT.
# At the old 06:30 slot the brief saw ~13h30m and missed the entire European
# close and the pre-open ramp, which is exactly where an overnight range gets
# resolved. The trade for that richness is lead time: the plan now lands 15
# minutes before the open, so a failure here has no second chance before the
# bell. Failures alert (see below) rather than failing silent.
#
# ORDERING. corpus-daily still runs at 06:30 and fills data/corpus/<day>/, so by
# 08:15 the day-dir exists and run.py's own datastream gate PASSES. Running the
# parse before that fill is what forces --no-gate (as an in-session 04:08 run on
# 2026-07-30 discovered). Do not move this earlier than the corpus fill.
#
# CRON PATH AND az [st-i68]. The letter is fetched from the enterprise Azure blob
# container, and on this box `az` is the WINDOWS CLI reached through WSL interop
# — it lives on the interactive PATH only. Cron's minimal PATH does not carry
# it, which is how the 2026-07-24 06:30 batch died on a bare FileNotFoundError.
# runbook/mancini/fetch.py:resolve_az() now searches explicit fallbacks, but this
# wrapper pins STRADER_AZ_BIN as well so the resolution never depends on which
# PATH cron happened to hand us.
#
# ALERTING. The old inline step called corpus_daily.emit_alert() on failure,
# which appends a durable line to data/corpus/_health.jsonl. That contract is
# preserved by importing the same function rather than re-implementing the record
# shape here — the health log is read by the gate and by the morning heartbeat
# (st-66u), so a second writer with a drifting schema would be worse than no
# alert at all.
#
# Manual smoke (safe — the blob fetch is cached, the parse is idempotent):
#   scripts/cron/mancini-preopen-wrapper.sh
# Explicit letter file instead of the blob fetch:
#   scripts/cron/mancini-preopen-wrapper.sh --file /tmp/letter.txt

set -uo pipefail

STRADER_REPO="${STRADER_REPO:-/root/projects/Strader}"
STRADER_VENV="${STRADER_VENV:-$STRADER_REPO/.venv}"
PY="$STRADER_VENV/bin/python"

: "${HOME:=/root}"
export HOME

# az resolution, pinned for cron. Only set if we did not inherit an override and
# the interop binary is actually there — an STRADER_AZ_BIN pointing at nothing
# would be worse than leaving resolve_az() to its own search.
AZ_INTEROP="/mnt/c/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin/az"
if [[ -z "${STRADER_AZ_BIN:-}" && -x "$AZ_INTEROP" ]]; then
    export STRADER_AZ_BIN="$AZ_INTEROP"
fi
export PATH="$PATH:$(dirname "$AZ_INTEROP")"

# --clip [st-0x9, st-llor, narrowed by st-lw58]. In prepare-only mode the only
# clipboard action left to this job is the good case: an in-session parse
# already ran overnight, its payload is hours stale by 08:15, and --clip
# authorizes reloading that RICHER stored parse so the morning routine finds
# the best payload waiting. When no parse exists yet, prepare-only never
# touches the clipboard — there is no plan to load, and the alert says so.
#
# Overridable to "" so this wrapper can be smoke-tested end to end without
# taking Steve's clipboard — a job that cannot be exercised without a side
# effect on his desktop will not get exercised:
#   STRADER_MANCINI_CLIP="" scripts/cron/mancini-preopen-wrapper.sh
CLIP_ARG="${STRADER_MANCINI_CLIP---clip}"

LOG_DIR="${STRADER_MANCINI_LOGDIR:-/var/moo/logs/mancini-preopen}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

log() { echo "[$(date +%H:%M:%S)] $*"; }

{
    log "=== mancini-preopen start $(date +%Y-%m-%dT%H:%M:%S%z) ==="
    log "repo=$STRADER_REPO az=${STRADER_AZ_BIN:-<resolve_az search>} args=${*:-<none>}"

    if [[ ! -x "$PY" ]]; then
        log "FATAL: venv python not executable: $PY"; exit 2
    fi

    cd "$STRADER_REPO" || { log "FATAL: repo dir missing: $STRADER_REPO"; exit 2; }

    # --prepare-only [st-lw58, ruled 2026-08-06]: this job never parses.
    # It fetches, cleans, scrapes the deterministic lists, then alerts "ready
    # to parse" — Steve triggers every real parse in-session (/mancini-parse).
    # When an in-session parse already exists it (a) reloads the richer payload
    # into the clipboard and (b) re-renders the SAME plan doc with the level-
    # interaction window brought from the letter's write-time to now
    # [st-vxbw, Steve 2026-08-18] — the parse may have run at 01:28 CT, and
    # its section covered a slice of the overnight. Levels are never touched;
    # no browser window from cron. Manual, with a browser window:
    #   PYTHONPATH=. .venv/bin/python -m runbook.mancini.refresh --open
    PYTHONPATH="$STRADER_REPO" "$PY" -m runbook.mancini.run --from-blob --prepare-only $CLIP_ARG "$@"
    rc=$?
    log "=== mancini-preopen end $(date +%Y-%m-%dT%H:%M:%S%z) (rc=$rc) ==="

    if (( rc != 0 )); then
        # Same alert kind and health-log contract the inline corpus_daily step used.
        MANCINI_RC="$rc" PYTHONPATH="$STRADER_REPO" "$PY" - <<'PYEOF' || log "WARN: alert emission failed"
import os
import sys

sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert

rc = int(os.environ["MANCINI_RC"])
emit_alert(
    "mancini_parse",
    f"Pre-open Mancini parse failed (rc={rc}) — last-good artifacts still stand; "
    "run manually or in-session. Cash open is 15 minutes out.",
    {"returncode": rc, "source": "mancini-preopen-wrapper"},
)
PYEOF
    fi

    exit $rc
} >> "$LOG" 2>&1
