#!/usr/bin/env bash
# corpus-compact-wrapper.sh — T+1 pack of a finished corpus day. [st-itky]
#
#   30 7 * * 1-6 /usr/bin/bash /root/projects/Strader/scripts/cron/corpus-compact-wrapper.sh
#
# Runs one hour behind corpus-daily (30 6 * * 1-6), which pulls the same day and
# took ~18 minutes on its heaviest recent run. Same day-range as that job so a
# Saturday pull of Friday's tape gets packed the same morning.
#
# WHY THIS EXISTS AT ALL. ES MBP-1 measures 1.6-2.9 GB per RTH day. Nothing had
# ever been compacted — there was not one .dbn.zst or .jsonl.gz in a 92 GB
# corpus — and Phase B round-the-clock capture multiplies that. Packing must be
# routine BEFORE the volume arrives, not after the disk is a problem.
#
# WHAT IT PACKS (scripts/corpus_compact_databento.py):
#   databento_*.{N}.dbn  -> .dbn.zst   (zstandard, still DBNStore-readable)
#   databento_*.jsonl    -> .jsonl.gz  (stdlib gzip)
# The uncompressed source is REMOVED after a verified compress. That is safe
# only because readers were taught to resolve either form first (st-itky:
# market.corpus.paths.resolve_existing / open_corpus_text, replay.has_es_day).
# If you are reading this because a day went missing, check that a reader is not
# still calling `es_day_path(day).exists()` — that returns False for a packed
# day and skips it in silence.
#
# NEVER PACK A PARTIAL PULL. The target day is only compacted once its manifest
# shows every required Databento stream present with cycles>0 and no errors.
# corpus-daily is idempotent and re-pulls an unhealthy stream on its next run,
# so a day that fails this check is left raw and picked up tomorrow — packing it
# now would freeze a half-written file into the archive.
#
# PATH IS SET EXPLICITLY [st-i68]. Cron's minimal PATH is why the 2026-07-24
# Mancini batch died on a bare `FileNotFoundError: 'az'`. Nothing here shells out
# to a Windows binary, but the same discipline applies.
set -uo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
LOG_DIR="${STRADER_COMPACT_LOGDIR:-/var/moo/logs/corpus-compact}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

# Streams that must be healthy before the day is considered packable. MBP-1 is
# deliberately NOT required: it exists only for days we pulled it for, and a
# trades-only day is still complete on its own terms.
REQUIRED="${STRADER_COMPACT_REQUIRED:-databento_glbx_es,databento_opra}"

{
    echo "=== corpus-compact start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

    if [[ ! -x "$PY" ]]; then
        echo "FATAL: venv python not executable: $PY"
        exit 2
    fi

    cd "$REPO" || { echo "FATAL: repo dir missing: $REPO"; exit 2; }

    # Resolve the target day and vet its manifest in one shot. Prints the day on
    # stdout when packable, or SKIP:<reason>. Uses the same helper corpus_daily
    # targets, so the two jobs cannot drift onto different days.
    DAY_OUT="$(PYTHONPATH="$REPO" "$PY" - "$REQUIRED" <<'PYEOF'
import json, sys
from market.corpus.paths import most_recent_session_day, manifest_path

required = [s for s in sys.argv[1].split(",") if s]
day = most_recent_session_day()
mf = manifest_path(day)
if not mf.exists():
    print(f"SKIP:no manifest for {day}")
    raise SystemExit(0)
try:
    streams = json.loads(mf.read_text(encoding="utf-8")).get("streams", {})
except (OSError, ValueError) as e:
    print(f"SKIP:unreadable manifest for {day} ({e})")
    raise SystemExit(0)
for name in required:
    s = streams.get(name)
    if not s:
        print(f"SKIP:{day} missing stream {name}")
        raise SystemExit(0)
    if not s.get("cycles"):
        print(f"SKIP:{day} stream {name} has no cycles")
        raise SystemExit(0)
    if s.get("errors"):
        print(f"SKIP:{day} stream {name} has errors")
        raise SystemExit(0)
print(day.isoformat())
PYEOF
)"
    rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "FATAL: day resolution failed (rc=$rc): $DAY_OUT"
        exit $rc
    fi

    if [[ "$DAY_OUT" == SKIP:* ]]; then
        echo "skip — ${DAY_OUT#SKIP:}"
        echo "=== corpus-compact end $(date -u +%Y-%m-%dT%H:%M:%SZ) (rc=0, no-op) ==="
        exit 0
    fi

    echo "target day = $DAY_OUT  (required healthy: $REQUIRED)"
    du -sh "data/corpus/$DAY_OUT" 2>/dev/null | sed 's/^/  before: /'

    PYTHONPATH="$REPO" "$PY" "$REPO/scripts/corpus_compact_databento.py" \
        --date "$DAY_OUT"
    rc=$?

    du -sh "data/corpus/$DAY_OUT" 2>/dev/null | sed 's/^/  after:  /'
    df -h / 2>/dev/null | tail -1 | sed 's/^/  disk:   /'
    echo "=== corpus-compact end $(date -u +%Y-%m-%dT%H:%M:%SZ) (rc=$rc) ==="
    exit $rc
} >>"$LOG" 2>&1
