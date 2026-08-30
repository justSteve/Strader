#!/usr/bin/env bash
# corpus-daily-wrapper.sh — launcher for the daily corpus batch pull. [st-4jkq]
#
#   OnCalendar=Mon..Sat 06:30 America/Chicago  (systemd timer, generated from
#   COO's SCHEDULE.md entry — see OWNERSHIP below; the crontab line it replaced
#   was `30 6 * * 1-6`)
#
# Ported from COO's factory/cron/corpus-daily-wrapper.sh [co-yva5] on the
# handback of 2026-08-13 (docs/a2a/2026-08-13-coo-to-strader-corpus-cron-handback.md,
# belled by COO 2026-08-30, ACKed the same day). The seam it closes: COO's unit
# launched Strader's venv, Strader's orchestrator and Strader's spend.
#
# OWNERSHIP, and why the unit is NOT in deploy/systemd/. The job is Strader's;
# the *catalog entry* stays in COO's SCHEDULE.md and the unit stays generated
# from it by factory/scripts/schedule-timers.sh. Two reasons, both measured:
# (1) deploy/install.sh copies deploy/systemd/* over /etc/systemd/system/, and
#     schedule-timers.sh generates the same filenames — one path, two writers,
#     which is a worse seam than the one being closed. Both generated units say
#     so in their own headers.
# (2) SCHEDULE.md holds the dependency graph, and two Strader jobs gate on this
#     node: strader-mancini-preopen (08:15) and strader-preopen-heartbeat (08:25)
#     both carry depends_on: ["coo-corpus-daily"]. deploy/install.sh has no
#     dependency model — it installs units and enables timers. A missed or late
#     06:30 run forces --no-gate at 08:15, and that edge is what catches it.
#
# NO CLAUDE SESSION. Pure deterministic Python: scripts/corpus_daily.py in this
# repo's venv. It pulls the most-recent-COMPLETED session's gate-required
# Databento streams (ES front-month, T+1 batch — the nightly SPXW OPRA pull was
# dropped 2026-08-17, co-03ojd.14), evaluates the datastream gate, and exits
# non-zero + alerts on any unhealthy stream. Gate-date policy is decision "A"
# (target the completed session), which corpus_daily.py resolves by default.
#
# SPEND. This job pulls paid Databento data. Ownership includes owning the
# switch — config/entitlements.yaml is the registry, probed, never recalled.
#
# rc contract (unchanged from the COO copy, and the unit's failed state is what
# /tap-in's HEARTBEATS check reads):
#   0  healthy
#   1  unhealthy — the alert is already in data/corpus/_health.jsonl
#   2  infra (venv, orchestrator or repo missing)
#
# Scope note: T+1 BATCH cadence only. Intraday Schwab cycles are a separate,
# higher-frequency schedule — not this wrapper.
#
# Manual smoke (no spend):  CORPUS_DRY_RUN=1 bash scripts/cron/corpus-daily-wrapper.sh
# Manual real run:          bash scripts/cron/corpus-daily-wrapper.sh
# Explicit day / options:   bash scripts/cron/corpus-daily-wrapper.sh --date 2026-06-30

set -uo pipefail

# Local constants — the COO copy sourced factory/factory.env only to resolve
# these two, and that cross-repo source is what the handback removes.
STRADER_REPO="/root/projects/Strader"
STRADER_VENV="$STRADER_REPO/.venv"

LOG_DIR="/var/moo/logs/corpus-daily"
mkdir -p "$LOG_DIR"
# CT, not UTC. The COO copy named the log by the UTC date; at 06:30 CT the two
# agree, so the scheduled run's address is unchanged — but a manual run after
# 19:00 CT landed in tomorrow's file. Human-facing stamps render Central here.
DATE="$(TZ=America/Chicago date +%Y-%m-%d)"
LOG="$LOG_DIR/$DATE.log"

PY="$STRADER_VENV/bin/python"
SCRIPT="$STRADER_REPO/scripts/corpus_daily.py"

# Dry-run passthrough for smoke tests without touching the paid feed.
EXTRA_ARGS=("$@")
if [[ "${CORPUS_DRY_RUN:-0}" == "1" ]]; then
    EXTRA_ARGS+=(--dry-run)
fi

{
    echo "=== corpus-daily start $(TZ=America/Chicago date +%Y-%m-%dT%H:%M:%S%z) ==="
    echo "STRADER_REPO=$STRADER_REPO  DRY_RUN=${CORPUS_DRY_RUN:-0}  ARGS=${EXTRA_ARGS[*]:-<none>}"

    if [[ ! -x "$PY" ]]; then
        echo "FATAL: Strader venv python not executable: $PY"
        exit 2
    fi
    if [[ ! -f "$SCRIPT" ]]; then
        echo "FATAL: orchestrator missing: $SCRIPT"
        exit 2
    fi

    cd "$STRADER_REPO" || { echo "FATAL: Strader repo dir missing: $STRADER_REPO"; exit 2; }
    PYTHONPATH="$STRADER_REPO" "$PY" "$SCRIPT" "${EXTRA_ARGS[@]}"
    rc=$?
    echo "=== corpus-daily end $(TZ=America/Chicago date +%Y-%m-%dT%H:%M:%S%z) (rc=$rc) ==="
    exit $rc
} >> "$LOG" 2>&1
