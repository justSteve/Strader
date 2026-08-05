#!/usr/bin/env bash
# capture-supervisor-session.sh — session-window capture supervision. [st-6qx4, st-btu]
#
#   */2 * * * * /usr/bin/bash /root/projects/Strader/scripts/cron/capture-supervisor-session.sh
#
# WHY THIS THIN WRAPPER EXISTS. capture-supervisor-wrapper.sh defaults to
# round-the-clock (START_CT=00:00, UNTIL_CT=23:59). That default is a capture-
# window decision, and the window is a ruling Steve reserved (st-btu). Rather
# than bury it in a crontab env prefix — which .claude/rules/no-env-prefix-commands.md
# rules out, because an assignment prefix hides the real command from the
# permission allow-list and cannot be smoke-tested the way it runs — the window
# lives here, in a checked-in file, where a diff shows it changing.
#
# THE RULING (Steve, 2026-08-05): live capture covers the SESSION only; the
# uncovered hours are backfilled afterwards. The reason the window stopped being
# a spend question is that GLBX historical turned out to be $0.00 under the
# current Databento Futures plan — measured, not assumed:
#
#     ES trades   2026-08-05 02:50-06:45 CT   $0.0000
#     ES mbp-1    2026-08-05 02:50-06:45 CT   $0.0000
#     ES mbp-1    2026-07-31 02:50-15:05 CT   $0.0000   (full settled day)
#     OPRA SPXW   2026-07-31 13:00-15:00 CT   $6.0663   (control: the estimator
#                                                        does return non-zero)
#
# So overnight and evening Globex do not need a live process at all — live
# capture is only genuinely required for what the live surface consumes DURING
# the session. Everything else is a free next-day pull. That buys 24h coverage
# without asking a long-lived process to survive 24h, which is precisely the
# thing that failed on 2026-08-05 (capture died at the prior day's 15:05 stop
# and nothing restarted it; found dead at 06:41, 1h49m before the open).
#
# WINDOW. 02:50 start matches the hand-run practice this replaces and gives the
# recognizer the pre-market hours st-btu cares about — 2026-07-22's marquee
# Failed Breakdown printed 07:56:53 CT, 34 minutes before the RTH corpus window
# opens, and the recognizer saw only its RTH echo. 15:05 stop matches the
# invocation that has been used by hand all along, so installing this implies
# no change to what gets captured live.
#
# Everything else — process-not-window identity, restart safety, staleness
# detection, health-log alerting — belongs to the supervisor itself. Read its
# header before changing anything here.
#
# Manual smoke (safe: idempotent, and a no-op while capture is healthy):
#   bash scripts/cron/capture-supervisor-session.sh

set -uo pipefail

export STRADER_CAPTURE_START_CT="${STRADER_CAPTURE_START_CT:-02:50}"
export STRADER_CAPTURE_UNTIL_CT="${STRADER_CAPTURE_UNTIL_CT:-15:05}"

exec /usr/bin/bash "$(dirname "$0")/capture-supervisor-wrapper.sh" "$@"
