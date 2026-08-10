#!/usr/bin/env bash
# gexbot-orderflow-1s-supervisor.sh — keep the LIVE 1 Hz orderflow leg alive,
# in session. [st-ipn0]
#
#   */2 * * * * /usr/bin/bash /root/projects/Strader/scripts/cron/gexbot-orderflow-1s-supervisor.sh
#
# Thin env wrapper over capture-supervisor-wrapper.sh, exactly like
# gexbot-supervisor-session.sh — read that file's header (and the wrapper's)
# before changing anything here. This file contributes only the facts below.
#
# WHY A THIRD SUPERVISOR. The 1 Hz leg (scripts/corpus_poll_gexbot_orderflow_1s.py)
# is a separate process from the 10-endpoint collector on purpose: different
# cadence, different failure economics (a stuck 1 Hz loop burns quota ~60x
# faster), and the main collector must not die because the high-rate leg does.
# Separate process, separate window, separate state file, same alert log.
#
# STALE AT 300s. The leg batches its manifest bump every 60 polls (~80s at the
# 1.1s interval), so 300s of no advance is 3+ missed batches — unambiguous.
#
# VENUE=cash, WINDOW 08:30-15:05 CT — identical reasoning to the main GexBot
# supervisor: the feed is frozen outside cash hours (measured), and NYSE
# holidays are dead all day.

set -uo pipefail

REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
POLLER="$REPO/scripts/corpus_poll_gexbot_orderflow_1s.py"

export STRADER_CAPTURE_LABEL="${STRADER_CAPTURE_LABEL:-gexbot 1Hz orderflow leg}"
export STRADER_CAPTURE_VENUE="${STRADER_CAPTURE_VENUE:-cash}"
export STRADER_CAPTURE_STREAMS="${STRADER_CAPTURE_STREAMS:-gexbot_orderflow_1s}"
export STRADER_CAPTURE_START_CT="${STRADER_CAPTURE_START_CT:-08:30}"
export STRADER_CAPTURE_UNTIL_CT="${STRADER_CAPTURE_UNTIL_CT:-15:05}"
export STRADER_CAPTURE_STALE_SECS="${STRADER_CAPTURE_STALE_SECS:-300}"
export STRADER_CAPTURE_STREAMER="${STRADER_CAPTURE_STREAMER:-$POLLER}"
export STRADER_CAPTURE_MATCH="${STRADER_CAPTURE_MATCH:-corpus_poll_gexbot_orderflow_1s.py}"

# Own state file — sharing one with either sibling supervisor would cross their
# cycle counts and cry stale every two minutes.
export STRADER_CAPTURE_STATE="${STRADER_CAPTURE_STATE:-$REPO/data/corpus/_gexbot_of1s_health.json}"
# ALERT log deliberately NOT overridden — data/corpus/_health.jsonl is the one
# surface read every morning.

export STRADER_CAPTURE_WIN="${STRADER_CAPTURE_WIN:-gexbot-of1s}"
export STRADER_CAPTURE_LOGDIR="${STRADER_CAPTURE_LOGDIR:-/var/moo/logs/gexbot-supervisor}"

export STRADER_CAPTURE_LAUNCH="${STRADER_CAPTURE_LAUNCH:-exec env PYTHONPATH=$REPO $PY $POLLER --start-ct $STRADER_CAPTURE_START_CT --until-ct $STRADER_CAPTURE_UNTIL_CT}"

exec /usr/bin/bash "$(dirname "$0")/capture-supervisor-wrapper.sh" "$@"
