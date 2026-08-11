#!/usr/bin/env bash
# premarket-vp-wrapper.sh — Build the premarket anchored volume profile. [st-eo0]
#
#   16 8 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/premarket-vp-wrapper.sh
#
# Steve, 2026-08-11: a volume profile anchored on the PRIOR DAY'S RTH OPEN
# (08:30 CT), published as a page in the Desk's Trading window, generated in
# premarket "alongside the Mancini prep".
#
# WHY 08:16 AND NOT 08:15. It shares the Mancini slot by intent, but not the
# same minute. Both jobs hit the same Schwab price-history endpoint for /ES
# 5-minute ETH bars; firing them concurrently races one token refresh against
# another for no gain. One minute later costs nothing (the profile moves by one
# bar at most) and keeps the two jobs from interleaving in the logs, which is
# what you actually want when diagnosing a bad morning.
#
# HARD DEPENDENCY: THE SCHWAB TOKEN. This job has no offline fallback. The tick
# corpus captures 02:50-15:05 CT only, so it cannot cover the evening session
# the anchor window spans; Schwab ETH bars are the sole continuous source. A
# dead refresh token means no page. That is why failure alerts rather than
# exiting quietly — see market/orderflow/anchored_profile.py for the full
# reasoning on source choice.
#
# FAILURE = LAST-GOOD. premarket_volume_profile.py leaves the previously
# published page in place on a fetch failure and exits 2. The page stamps its
# own anchor and generated-at time in the header, so a stale page reads as
# visibly stale instead of quietly wrong.
#
# Manual smoke (safe — read-only GET, and --dry-run publishes nothing):
#   scripts/cron/premarket-vp-wrapper.sh --dry-run

set -uo pipefail

STRADER_REPO="${STRADER_REPO:-/root/projects/Strader}"
STRADER_VENV="${STRADER_VENV:-$STRADER_REPO/.venv}"
PY="$STRADER_VENV/bin/python"

: "${HOME:=/root}"
export HOME

LOG="${STRADER_LOG_DIR:-$STRADER_REPO/logs}/premarket-vp.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "$*"; }

{
    log "=== premarket-vp start $(date +%Y-%m-%dT%H:%M:%S%z) ==="

    PYTHONPATH="$STRADER_REPO" "$PY" "$STRADER_REPO/scripts/premarket_volume_profile.py" "$@"
    rc=$?
    log "=== premarket-vp end $(date +%Y-%m-%dT%H:%M:%S%z) (rc=$rc) ==="

    if (( rc != 0 )); then
        # Same health-log contract every other Strader cron uses, so the gate
        # and the morning heartbeat see this failure the way they see the rest.
        VP_RC="$rc" PYTHONPATH="$STRADER_REPO" "$PY" - <<'PYEOF' || log "WARN: alert emission failed"
import os
import sys

sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert

rc = int(os.environ["VP_RC"])
emit_alert(
    "premarket_vp",
    f"Premarket anchored volume profile failed (rc={rc}) — the previously "
    "published page still stands and is now STALE. Most likely cause is a dead "
    "Schwab refresh token; this job has no offline source.",
    {"returncode": rc, "source": "premarket-vp-wrapper"},
)
PYEOF
    fi

    exit $rc
} >> "$LOG" 2>&1
