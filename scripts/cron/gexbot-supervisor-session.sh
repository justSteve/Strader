#!/usr/bin/env bash
# gexbot-supervisor-session.sh — keep the GexBot collector alive, in session. [st-p3lv]
#
#   */2 * * * * /usr/bin/bash /root/projects/Strader/scripts/cron/gexbot-supervisor-session.sh
#
# WHAT THIS REPLACES. The collector was started by hand in a tmux pane on
# 2026-08-05 and supervised by nothing. On 2026-08-05 ~19:56 CT the moocity tmux
# server died and took it down with the /hist backfill; nothing restarted either
# and nothing alerted (st-p3lv, Steve's incident note). Then the opposite failure:
# left running, it collected 1153 cycles across Saturday 2026-08-08 on a closed
# market — 58.4 MB — and died unattended at 01:30 Sunday. Unsupervised in both
# directions at once.
#
# TWO HALVES, DELIBERATELY SEPARATE.
#   * The SESSION GATE lives in scripts/corpus_poll_gexbot.py, so a hand-run pane
#     is gated too. A gate that only exists in the scheduler protects nothing that
#     someone starts by hand — and by hand is how this ran every day of its life.
#   * RESTART lives here, because a process cannot restart itself. Cron is the
#     right host precisely because it is not tmux: the 08-05 incident killed a
#     tmux-hosted supervisor along with the thing it supervised.
#
# WHY IT IS A THIN WRAPPER. Everything hard — process-not-window identity, the
# alive-but-not-receiving verdict, restart safety, the shared health log, the
# refusal to relaunch into the last two minutes of a window — is already solved
# in capture-supervisor-wrapper.sh for the ES streamer. A second copy of that
# reasoning is a second place for it to rot. Read that file's header before
# changing anything here; this file contributes only the six facts below.
#
# VENUE=cash [st-p3lv]. The ES supervisor deliberately does not model holidays,
# because CME equity-index futures trade shortened sessions on most NYSE closures
# — calling those days closed would suppress a real `stale`. GexBot has no such
# ambiguity: Thanksgiving is dead all day. `--venue cash` consults the NYSE
# holiday table in strader/market_calendar.py, so a holiday reports `idle` and
# this supervisor stands down instead of relaunching a collector that would exit
# on its own gate every two minutes for seven hours.
#
# WINDOW 08:30-15:05 CT — measured, not assumed. This said 07:30 for one day, on
# a belief about a pre-open ramp that turned out to be false: the GexBot feed is
# frozen at a single value from midnight until 08:30:02 CT, when it takes its
# first new value at the cash open to the second. See the constants block in
# scripts/corpus_poll_gexbot.py for the full measurement. 15:05
# matches capture-supervisor-session.sh's stop, so both live feeds close the day
# on the same boundary. The window is duplicated in the launch command on purpose:
# the collector enforces it, the supervisor merely agrees. If they ever disagree,
# the collector wins by exiting and the supervisor reports it, which is the safe
# direction.
#
# STALE AT 300s, NOT 600s. The ES default is generous because ES ticks many times
# a second and ten quiet minutes is unambiguous death. GexBot commits one cycle a
# minute, so five missed cycles is already a clear signal and waiting ten costs
# five more.
#
# Manual smoke (safe: idempotent, and a no-op while the collector is healthy or
# the market is closed):
#   bash scripts/cron/gexbot-supervisor-session.sh

set -uo pipefail

REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
POLLER="$REPO/scripts/corpus_poll_gexbot.py"

export STRADER_CAPTURE_LABEL="${STRADER_CAPTURE_LABEL:-gexbot collector}"
export STRADER_CAPTURE_VENUE="${STRADER_CAPTURE_VENUE:-cash}"
export STRADER_CAPTURE_STREAMS="${STRADER_CAPTURE_STREAMS:-gexbot}"
export STRADER_CAPTURE_START_CT="${STRADER_CAPTURE_START_CT:-08:30}"
export STRADER_CAPTURE_UNTIL_CT="${STRADER_CAPTURE_UNTIL_CT:-15:05}"
export STRADER_CAPTURE_STALE_SECS="${STRADER_CAPTURE_STALE_SECS:-300}"
export STRADER_CAPTURE_STREAMER="${STRADER_CAPTURE_STREAMER:-$POLLER}"
export STRADER_CAPTURE_MATCH="${STRADER_CAPTURE_MATCH:-corpus_poll_gexbot.py}"

# Its own state file. Sharing _capture_health.json with the ES supervisor would
# make each run inherit the other's cycle counts and cry stale every two minutes.
export STRADER_CAPTURE_STATE="${STRADER_CAPTURE_STATE:-$REPO/data/corpus/_gexbot_health.json}"
# The ALERT log is deliberately NOT overridden: data/corpus/_health.jsonl is the
# one surface read every morning, and a second log would be a second thing to
# forget to read.

# Its own tmux window, and NOT `gexbot-collect` — that is the name the hand-run
# pane used, and reusing it would make a supervisor relaunch indistinguishable
# from Steve's own pane in `tmux list-windows`.
export STRADER_CAPTURE_WIN="${STRADER_CAPTURE_WIN:-gexbot}"
export STRADER_CAPTURE_LOGDIR="${STRADER_CAPTURE_LOGDIR:-/var/moo/logs/gexbot-supervisor}"

export STRADER_CAPTURE_LAUNCH="${STRADER_CAPTURE_LAUNCH:-exec env PYTHONPATH=$REPO $PY $POLLER --start-ct $STRADER_CAPTURE_START_CT --until-ct $STRADER_CAPTURE_UNTIL_CT}"

exec /usr/bin/bash "$(dirname "$0")/capture-supervisor-wrapper.sh" "$@"
