#!/usr/bin/env bash
# schwab-stages-wrapper.sh — Schwab quote/chain snapshot at session-stage boundaries. [st-096]
#
#   0  7  * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/schwab-stages-wrapper.sh premarket
#   30 8  * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/schwab-stages-wrapper.sh open
#   0  13 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/schwab-stages-wrapper.sh afternoon
#   45 14 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/schwab-stages-wrapper.sh close-watch
#
# Cron runs local America/Chicago time (same convention as the gauge heartbeat),
# so the boundaries track the 08:30 cash open and ride DST automatically.
#
# WHY STAGE BOUNDARIES, NOT A POLL LOOP. Each fire is one REST pull (free, no
# metering, no streamer session — so it can never collide with Steve's ToS
# login, the one-streaming-session constraint recorded on st-096). Four
# snapshots bracket the session's decision points:
#   premarket  (07:00) — the ES quote's session high/low at this hour IS the
#                        overnight range; closes the "no wired overnight quote"
#                        gap from preview day 1
#   open       (08:30) — cash open reference
#   afternoon  (13:00) — butterfly window opens; last calm look before the play
#   close-watch(14:45) — 15 min of lead before the 15:00 close
#
# Each record lands in data/corpus/<today>/schwab.jsonl stamped with its stage
# label, and the manifest carries the schwab stream again — the AC this cron
# exists to satisfy. The pull script is append-only and each boundary fires
# once, so a cron retry costs one extra row, never corruption.
#
# FAILURE SURFACE. Non-zero exit appends a schwab_pull alert to
# data/corpus/_health.jsonl via corpus_daily.emit_alert — the same contract the
# Mancini wrapper uses, read by the morning heartbeat (st-66u). Token-age
# warnings are NOT this wrapper's job: the st-e2f heartbeat riding the 06:30
# corpus batch warns days before expiry; by the time a pull here fails on auth,
# that alarm has already fired twice.
#
# Manual smoke (LIVE API — Steve runs it, or approves the run):
#   scripts/cron/schwab-stages-wrapper.sh adhoc

set -uo pipefail

STRADER_REPO="${STRADER_REPO:-/root/projects/Strader}"
STRADER_VENV="${STRADER_VENV:-$STRADER_REPO/.venv}"
PY="$STRADER_VENV/bin/python"

: "${HOME:=/root}"
export HOME

STAGE="${1:-adhoc}"

LOG_DIR="${STRADER_SCHWAB_LOGDIR:-/var/moo/logs/schwab-stages}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Heartbeat [co-8b60y]: /var/moo/state/strader-schwab-<stage>.json — running at
# start, ok/failed on exit by the trap heartbeat-lib.sh arms. One file per stage
# so a failed 07:00 is not hidden by a good 08:30. Read by COO's
# heartbeat-check.sh at /tap-in.
# shellcheck source=heartbeat-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/heartbeat-lib.sh"
hb_init "$(hb_path "strader-schwab-$STAGE")" "stage $STAGE"

{
    log "=== schwab-stages start stage=$STAGE $(date +%Y-%m-%dT%H:%M:%S%z) ==="

    if [[ ! -x "$PY" ]]; then
        log "FATAL: venv python not executable: $PY"; exit 2
    fi

    cd "$STRADER_REPO" || { log "FATAL: repo dir missing: $STRADER_REPO"; exit 2; }

    PYTHONPATH="$STRADER_REPO" "$PY" "$STRADER_REPO/scripts/corpus_pull_schwab.py" --stage "$STAGE"
    rc=$?
    log "=== schwab-stages end stage=$STAGE (rc=$rc) ==="

    if (( rc != 0 )); then
        SCHWAB_RC="$rc" SCHWAB_STAGE="$STAGE" PYTHONPATH="$STRADER_REPO" "$PY" - <<'PYEOF' || log "WARN: alert emission failed"
import os
import sys

sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert

rc = int(os.environ["SCHWAB_RC"])
stage = os.environ["SCHWAB_STAGE"]
emit_alert(
    "schwab_pull",
    f"Schwab {stage} snapshot failed (rc={rc}). If auth: Steve runs "
    "scripts/refresh_schwab_token.py (interactive OAuth). Later boundaries "
    "today will fail the same way until fixed.",
    {"returncode": rc, "stage": stage, "source": "schwab-stages-wrapper"},
)
PYEOF
    fi

    if (( rc == 0 )); then HB_DETAIL="$STAGE snapshot landed"
    else HB_DETAIL="Schwab $STAGE snapshot rc=$rc (token? see the alert) — $LOG"; fi
    exit $rc
} >> "$LOG" 2>&1
