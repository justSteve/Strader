#!/usr/bin/env bash
# corpus-compact-wrapper.sh — T+1 pack of finished corpus days. [st-itky]
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
# NEVER PACK A PARTIAL PULL. A day is packed only when the datastream gate
# (runbook/datastream/gate.py) passes it: every required stream present with
# cycles>0 and a last write that covers the session close, and no error that is
# not a transport note. Until 2026-09-04 this wrapper applied its own rule —
# "any error at all → skip" — which was stricter than the gate and never
# forgiving: one reconnect note left a day raw for good, and the 42-hour
# outage of 09-02/03 left 7 GB of whole, backfilled tape unpacked. The gate is
# the single verdict on a day's health; this job asks it rather than keeping a
# second opinion [co-8b60y].
#
# THE TRAILING SWEEP [co-8b60y]. The job used to look only at the most recent
# session day, so a day that failed the check once (an outage morning, a pull
# that landed after 07:30) was never looked at again. It now walks back
# STRADER_COMPACT_SWEEP_DAYS calendar days (default 7) from the most recent
# session day and packs every weekday in that window that still holds raw files
# and passes the gate — most recent first, one log line per day. A day the gate
# rejects is logged with the gate's reason and left raw for tomorrow's look.
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
# databento_opra was dropped from the default 2026-08-18 [st-9olq]: the OPRA plan
# was cancelled 2026-08-04 and its import halted 08-07, and requiring it left
# every day from 08-06 on unpacked ("skip — missing stream databento_opra" in
# /var/moo/logs/corpus-compact/, 2.2-4.4 GB a day raw against ~200 MB packed).
REQUIRED="${STRADER_COMPACT_REQUIRED:-databento_glbx_es}"
SWEEP_DAYS="${STRADER_COMPACT_SWEEP_DAYS:-7}"
# Test seam: pin "now" (ISO, US/Central) so the day window is reproducible.
NOW="${STRADER_COMPACT_NOW:-}"

# Heartbeat [co-8b60y]: /var/moo/state/strader-corpus-compact.json — running
# while it packs (SCHEDULE.md max_run_min 180: a sweep may pack several days),
# ok/failed on exit by the trap heartbeat-lib.sh arms, the counts in the detail.
# shellcheck source=heartbeat-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/heartbeat-lib.sh"
hb_init "$(hb_path strader-corpus-compact)" "T+1 pack, sweep $SWEEP_DAYS day(s)"

{
    echo "=== corpus-compact start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

    if [[ ! -x "$PY" ]]; then
        echo "FATAL: venv python not executable: $PY"
        exit 2
    fi

    cd "$REPO" || { echo "FATAL: repo dir missing: $REPO"; exit 2; }

    # Vet every candidate day in one shot. One line per day on stdout:
    #   PACK:<day>              the gate passed it and raw files remain
    #   SKIP:<day>:<reason>     left raw; the reason is the gate's own words
    # Most recent day first. Uses the same day helper corpus_daily targets, so
    # the two jobs cannot drift onto different days.
    VERDICTS="$(PYTHONPATH="$REPO" "$PY" - "$REQUIRED" "$SWEEP_DAYS" "$NOW" <<'PYEOF'
import sys
from datetime import datetime, timedelta
from market.corpus.paths import CENTRAL, day_dir, manifest_path, most_recent_session_day
from runbook.datastream import gate

required = tuple(s for s in sys.argv[1].split(",") if s)
sweep_days = max(0, int(sys.argv[2] or 0))
now = datetime.fromisoformat(sys.argv[3]).replace(tzinfo=CENTRAL) if sys.argv[3] else None

RAW = ("databento_*.dbn", "databento_*.jsonl")

def has_raw(ddir):
    return any(any(ddir.glob(p)) for p in RAW)

latest = most_recent_session_day(now)
days = [latest - timedelta(days=i) for i in range(sweep_days + 1)]
for day in days:
    if day.weekday() >= 5:
        continue                       # GLBX weekend segments are not sessions
    ddir = day_dir(day)
    if not ddir.exists() or not has_raw(ddir):
        continue                       # nothing raw to pack; not a finding
    if not manifest_path(day).exists():
        print(f"SKIP:{day.isoformat()}:no manifest")
        continue
    r = gate.check(day=day, required_streams=required)
    if r.ok:
        es = ", ".join(f"{n}={c.get('cycles')}" for n, c in r.checked.items()
                       if n in required and isinstance(c, dict))
        notes = "; ".join(r.warnings) if r.warnings else ""
        print(f"PACK:{day.isoformat()}:{r.status} {es}" + (f" — {notes}" if notes else ""))
    else:
        print(f"SKIP:{day.isoformat()}:{'; '.join(r.reasons)}")
PYEOF
)"
    rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "FATAL: day vetting failed (rc=$rc): $VERDICTS"
        exit $rc
    fi

    if [[ -z "$VERDICTS" ]]; then
        echo "nothing raw in the last $SWEEP_DAYS day(s) — nothing to pack"
        echo "=== corpus-compact end $(date -u +%Y-%m-%dT%H:%M:%SZ) (rc=0, no-op) ==="
        HB_DETAIL="nothing raw in the last $SWEEP_DAYS day(s)"
        exit 0
    fi

    packed=0; failed=0; skipped=0
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        case "$line" in
            SKIP:*)
                rest="${line#SKIP:}"; day="${rest%%:*}"; reason="${rest#*:}"
                echo "skip — $day: $reason"
                skipped=$((skipped + 1))
                ;;
            PACK:*)
                rest="${line#PACK:}"; day="${rest%%:*}"; verdict="${rest#*:}"
                echo "target day = $day  (gate: $verdict; required healthy: $REQUIRED)"
                du -sh "${STRADER_CORPUS_ROOT:-data/corpus}/$day" 2>/dev/null | sed 's/^/  before: /'
                PYTHONPATH="$REPO" "$PY" "$REPO/scripts/corpus_compact_databento.py" \
                    --date "$day"
                prc=$?
                du -sh "${STRADER_CORPUS_ROOT:-data/corpus}/$day" 2>/dev/null | sed 's/^/  after:  /'
                if [[ $prc -eq 0 ]]; then
                    echo "packed $day"
                    packed=$((packed + 1))
                else
                    echo "FAILED $day (rc=$prc) — source left in place"
                    failed=$((failed + 1))
                fi
                ;;
            *)
                echo "unexpected vetting line: $line"
                ;;
        esac
    done <<<"$VERDICTS"

    df -h / 2>/dev/null | tail -1 | sed 's/^/  disk:   /'
    rc=0; (( failed > 0 )) && rc=1
    echo "=== corpus-compact end $(date -u +%Y-%m-%dT%H:%M:%SZ) (rc=$rc; packed=$packed failed=$failed skipped=$skipped) ==="
    HB_DETAIL="packed $packed, failed $failed, skipped $skipped (gate-rejected, left raw)${failed:+}"
    (( failed > 0 )) && HB_DETAIL="$HB_DETAIL — $LOG"
    exit $rc
} >>"$LOG" 2>&1
