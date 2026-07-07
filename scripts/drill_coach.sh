#!/usr/bin/env bash
# drill_coach.sh — coach-side lifecycle + verbs for the drill bridge. [st-ago step 2]
#
# Step 1 built the bridge (scripts/drill_bridge.py, port 7788). This owns its
# LIFECYCLE (start/stop/status, idempotent) and gives a coach session clean
# verbs over the HTTP API instead of hand-rolled curl — so the coach role is
# skill-owned, not ad-hoc. Paired with .claude/skills/drill-coach/SKILL.md.
#
# Usage:
#   drill_coach.sh start|stop|restart|status      # bridge lifecycle
#   drill_coach.sh state                          # latest drill state (one shot)
#   drill_coach.sh tail [n]                        # last n bridge events
#   drill_coach.sh watch [n]                       # live state (for a tmux pane)
#   drill_coach.sh say "text"                      # caption into Steve's drill
#   drill_coach.sh arm <price> | jump <bar> | pause | play
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${DRILL_BRIDGE_PORT:-7788}"
BASE="http://127.0.0.1:${PORT}"
PY="${REPO}/.venv/bin/python"
RUN_DIR="${REPO}/data/drill-bridge"
PIDFILE="${RUN_DIR}/bridge.pid"
OUTLOG="${RUN_DIR}/bridge.out"

_health() { curl -s --max-time 2 "${BASE}/health" 2>/dev/null; }
_up() { _health | grep -q '"ok": *true'; }

_post_coach() {  # $1=json — the bridge json.loads the body regardless of content-type
  if ! _up; then echo "coach: bridge is down — run 'drill_coach.sh start'" >&2; return 1; fi
  local r; r=$(curl -s --max-time 3 -X POST "${BASE}/coach" -d "$1" 2>/dev/null)
  if grep -q '"ok": *true' <<<"$r"; then
    echo "→ sent (cmd #$(jq -r '.id' <<<"$r"))"
  else
    echo "coach: bridge rejected command: $r" >&2; return 1
  fi
}

cmd_start() {
  mkdir -p "$RUN_DIR"
  if _up; then echo "bridge already up on :${PORT} — $(_health | jq -c '{started,events,queued}')"; return 0; fi
  [ -x "$PY" ] || { echo "no venv python at $PY" >&2; return 1; }
  DRILL_BRIDGE_PORT="$PORT" nohup "$PY" "${REPO}/scripts/drill_bridge.py" >"$OUTLOG" 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 25); do _up && { echo "bridge up on :${PORT} (pid $(cat "$PIDFILE")) — log ${OUTLOG}"; return 0; }; sleep 0.2; done
  echo "bridge failed to become healthy; see ${OUTLOG}" >&2; return 1
}

cmd_stop() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" && echo "stopped bridge (pid $(cat "$PIDFILE"))"; rm -f "$PIDFILE"; return 0
  fi
  # fall back to matching the process if the pidfile is stale (ad-hoc launch)
  local pids; pids=$(pgrep -f "scripts/drill_bridge.py" || true)
  if [ -n "$pids" ]; then kill $pids && echo "stopped bridge (pid $pids, no pidfile — was ad-hoc)"; rm -f "$PIDFILE"; return 0; fi
  echo "no bridge running"
}

cmd_status() {
  if _up; then _health | jq .; else echo "bridge down (:${PORT})"; return 1; fi
}

cmd_state() {  # last drill-channel event, human-readable
  _health >/dev/null || { echo "bridge down"; return 1; }
  curl -s "${BASE}/state/tail?n=80" \
    | jq -r '[.events[] | select(.channel=="drill")] | last
             | if . == null then "no drill events yet (browser not connected?)"
               else "bar \(.bar // "?")  \(.clock // "--")  last \(.price // "?")  "
                    + "sessionΔ \(.session_delta // "?")  level \(.level // "none")  [\(.kind)]"
               end'
}

cmd_tail() {  # last n events, both channels
  local n="${1:-40}"
  curl -s "${BASE}/state/tail?n=${n}" \
    | jq -r '.events[] | "\(.logged[11:23] // "")  \(.channel // "sys" | ascii_upcase[0:5])  "
             + "\(.kind // .type // "?")  \(.clock // "")  \(if .price then "@\(.price)" else "" end)"
             + "\(if .text then " — \(.text)" else "" end)"'
}

cmd_watch() {  # continuous state for a human/tmux pane
  local n="${1:-1}"
  echo "watching ${BASE} (Ctrl-C to stop)…"
  while true; do printf '\r%-110s' "$(cmd_state 2>/dev/null)"; sleep 2; done
}

case "${1:-}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)  cmd_status ;;
  state)   cmd_state ;;
  tail)    cmd_tail "${2:-40}" ;;
  watch)   cmd_watch "${2:-1}" ;;
  say)     _post_coach "$(jq -nc --arg t "${2:?say needs text}" '{type:"say",text:$t}')" ;;
  arm)     _post_coach "$(jq -nc --argjson p "${2:?arm needs price}" '{type:"arm",price:$p}')" ;;
  jump)    _post_coach "$(jq -nc --argjson b "${2:?jump needs bar}" '{type:"jump",bar:$b}')" ;;
  pause)   _post_coach '{"type":"pause"}' ;;
  play)    _post_coach '{"type":"play"}' ;;
  *) sed -n '3,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
