#!/usr/bin/env bash
# capture-evening.sh — the evening half of the Globex day. [st-9olq]
#
# Steve, 2026-08-18: the premarket profile banners "the 15:05→02:50 CT evening
# session is MISSING" — because the capture window was 02:50–15:05 CT (st-btu),
# not because Databento lacks it. Cost is sub-covered (config/entitlements.yaml
# databento_plan; knowledge/databento-live-collection.md) and the disk was
# measured at 783 GB free, so the ruling was extended to the Globex day.
#
# Three windows, one process each, every one writing the CALENDAR day's
# directory (data/corpus/<CT date>/) so the per-day file contract every reader
# rests on is untouched:
#     early    00:00 → 02:50       strader-capture-early.timer   Mon..Fri
#     session  02:50 → 15:05       strader-capture.timer         Mon..Fri  (unchanged)
#     evening  15:06 → 23:59:59    strader-capture-evening.timer Mon..Fri + Sun 17:00
# Friday's evening ends at 16:05 CT: CME closes ES at 16:00 Friday and does not
# reopen until Sunday 17:00, so a Friday run to midnight would sit idle for eight
# hours. That one weekday rule is why this wrapper exists instead of a bare
# ExecStart. Handovers leave a ≤ 60 s gap on purpose (15:05→15:06; 02:50 with
# the timer's accuracy) rather than two processes appending to one file.
#
# The 15:15–15:30 pause and the 16:00–17:00 maintenance halt are quiet minutes
# inside a connected stream, not gaps in coverage; strader/capture_health.py's
# Globex calendar knows both, so the assessor does not call them stale.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
dow="$(TZ=America/Chicago date +%u)"       # 1=Mon … 5=Fri, 7=Sun
now_ct="${STRADER_CAPTURE_NOW_CT:-$(TZ=America/Chicago date +%H:%M)}"
until_ct="${STRADER_CAPTURE_EVENING_UNTIL_CT:-23:59:59}"
[[ "$dow" == "5" ]] && until_ct="${STRADER_CAPTURE_FRIDAY_UNTIL_CT:-16:05}"

# Refuse to start before the window opens. [st-sode, 2026-09-08]
# The service is WantedBy=multi-user.target, so a reboot starts it whatever the
# clock says; the streamer only refuses once its STOP time has passed, and the
# evening stop is 23:59:59, so a 03:03 CT boot on 09-08 started this unit next
# to strader-capture and both appended to one file for hours — every trade
# written twice, some out of order, the footprint feed down on the first
# out-of-order row. Exit 0 (not failure) so Restart=on-failure does not spin;
# the timer starts the real run at 15:06 / Sun 17:00.
opens_ct="15:06"
[[ "$dow" == "7" ]] && opens_ct="17:00"
if [[ "$dow" == "6" || "$now_ct" < "$opens_ct" ]]; then
    echo "capture-evening: $now_ct CT is before the $opens_ct CT open (dow=$dow); not starting — the timer will." >&2
    exit 0
fi
cd "$REPO" || exit 2
exec env PYTHONPATH="$REPO" "$PY" "$REPO/scripts/corpus_stream_databento.py" \
    --streams es,es-mbp1 --now --until-ct "$until_ct"
