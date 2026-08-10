#!/usr/bin/env bash
# eod-packet-wrapper.sh — gather the trading day's facts at the close. [st-z92a]
#
#   15 15 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/eod-packet-wrapper.sh
#
# WHAT THIS IS NOT. It is not the EOD ritual. It writes nothing to
# DaysActivity.md, grades no calls and draws no conclusions. It is the PREPARE
# half, and the split is the one Steve ruled for the Mancini job (st-lw58,
# 2026-08-06): cron prepares and alerts, the agent interprets in session. The
# ritual itself is `/eod`, which reads the packet this job leaves behind.
#
# WHY IT RUNS AT ALL, given the ritual needs an agent. The failure being fixed
# is 2026-08-08: five commits, no handoff, and a day that ended with no record
# anywhere but the commit log. If the facts only get gathered when someone is at
# the desk, the day nobody is at the desk is the day they are lost — and that is
# exactly the day worth having. Written to data/eod/<date>.md at 15:15, the facts
# survive whether or not the narrative ever gets written, and a day with a packet
# and no Day Close entry becomes a VISIBLE gap (eod_packet.py --audit, surfaced
# at tap-in) instead of a silent one.
#
# 15:15 CT. Fifteen minutes after the cash close, which is late enough that the
# GexBot collector has stopped (window ends 15:05) and the ES capture has closed
# its manifest, and early enough that the day is still live if Steve wants to run
# /eod on it before dinner. The Databento T+1 batch has NOT landed — that is on
# purpose; this packet describes what the LIVE feeds captured, which is the thing
# that cannot be re-collected tomorrow.
#
# 1-5 IN CRON IS NOT THE GATE. The holiday calendar lives in
# strader/market_calendar.py and eod_packet.py consults it — a holiday prints one
# line and exits 0 without writing a packet. The cron day-of-week field only
# saves two wasted fires a week.
#
# EXIT CODES. 0 = packet written, nothing urgent. 3 = packet written but it
# contains a HARD gap: a stream that collected nothing (unrecoverable — the tape
# cannot be re-collected) or GEX rows outside the collect window (the session
# gate has stopped holding, st-a6zm). Only 3 and hard failures alert. Soft gaps —
# an ungraded call, a missing Mancini entry — are for /eod to notice; an alert
# that fires most days is not an alert.
#
# Manual smoke (safe — read-only apart from data/eod/):
#   bash scripts/cron/eod-packet-wrapper.sh
#   bash scripts/cron/eod-packet-wrapper.sh --day 2026-08-07

set -uo pipefail

export PATH="/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

STRADER_REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$STRADER_REPO/.venv/bin/python}"

: "${HOME:=/root}"
export HOME

LOG_DIR="${STRADER_EOD_LOGDIR:-/var/moo/logs/eod-packet}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

log() { echo "[$(date +%H:%M:%S)] $*"; }

{
    log "=== eod-packet start $(date +%Y-%m-%dT%H:%M:%S%z) args=${*:-<none>} ==="

    if [[ ! -x "$PY" ]]; then
        log "FATAL: venv python not executable: $PY"; exit 2
    fi
    cd "$STRADER_REPO" || { log "FATAL: repo dir missing: $STRADER_REPO"; exit 2; }

    # The packet's Work section shells out to `bd` (/usr/local/bin) and `git`.
    # Both are covered by the explicit PATH above; a bare FileNotFoundError there
    # would silently drop half the section rather than fail loudly [st-i68].
    PYTHONPATH="$STRADER_REPO" "$PY" scripts/eod_packet.py "$@"
    rc=$?
    log "=== eod-packet end $(date +%Y-%m-%dT%H:%M:%S%z) (rc=$rc) ==="

    if (( rc != 0 )); then
        EOD_RC="$rc" PYTHONPATH="$STRADER_REPO" "$PY" - <<'PYEOF' || log "WARN: alert emission failed"
import os
import sys

sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert

rc = int(os.environ["EOD_RC"])
if rc == 3:
    msg = ("EOD packet written but it carries a HARD gap — a stream collected "
           "nothing, or GEX rows landed outside the collect window. Read "
           "data/eod/<today>.md; live tape cannot be re-collected tomorrow.")
else:
    msg = (f"EOD packet job failed (rc={rc}) — the trading day's facts were NOT "
           "gathered. Run scripts/eod_packet.py by hand before the day goes cold.")
emit_alert("eod_packet", msg, {"returncode": rc, "source": "eod-packet-wrapper"})
PYEOF
    fi
    exit $rc
} >> "$LOG" 2>&1
