---
name: checkpoint
description: Mini session checkpoint — auto-save state for crash recovery
allowed-tools: Bash, Read, Write
---

# Checkpoint — Mini Session Save

Lightweight state capture that runs on a timer. Designed to be invoked by `/loop 30m /checkpoint` so that if the session dies without a proper `/handoff`, the next `/tap-in` has something recent to work with.

**Keep this fast and quiet.** Minimal output to the user.

## Execution Model

**Always run as a background subagent.** When this skill is invoked (by cron, `/loop`, or manually), spawn a background Agent to do the work. The checkpoint must never block the main conversation.

```
Agent({
  description: "Checkpoint auto-save",
  run_in_background: true,
  prompt: "<the gather/write/log steps below, filled with repo path>"
})
```

Output one line after spawning: nothing — the agent reports "Checkpoint saved [HH:MM]" when it completes.

## Workflow (executed by the subagent)

### 1. Gather state

Run these in parallel:

```bash
# Git state
git -C "$CLAUDE_PROJECT_DIR" diff --stat HEAD 2>/dev/null || echo "no changes"
```

```bash
# Uncommitted files
git -C "$CLAUDE_PROJECT_DIR" status --porcelain 2>/dev/null | head -20
```

```bash
# Active beads
bd list --status in_progress 2>/dev/null | head -10
```

### 2. Write checkpoint

Write to `.claude/state/checkpoint.json`:

```json
{
  "zgent": "<repo basename>",
  "timestamp": "<ISO 8601 UTC>",
  "type": "checkpoint",
  "git": {
    "branch": "<current branch>",
    "dirty_files": ["<list from git status --porcelain>"],
    "diff_stat": "<git diff --stat summary line>"
  },
  "beads": {
    "in_progress": ["<id> — <title>"]
  },
  "note": "<one sentence: what appears to be happening based on recent context>"
}
```

### 3. Log it

```bash
jq -n -c \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" \
  --arg sid "${CLAUDE_SESSION_ID:-unknown}" \
  --arg zgent "$(basename "${CLAUDE_PROJECT_DIR:-$(pwd)}")" \
  --arg event "checkpoint" \
  '{ts:$ts, session_id:$sid, zgent:$zgent, event:$event}' \
  >> /var/moo/logs/sessions.jsonl 2>/dev/null || true
```

### 4. Output

One line only:

```
Checkpoint saved [HH:MM]
```

Do NOT produce a detailed summary. Do NOT ask the user anything. This runs in the background of an active session.

## Recovery

The next `/tap-in` should check for checkpoint.json when no snapshot.json exists:

- **snapshot.json exists** → full warm start (from /handoff) — ignore checkpoint
- **checkpoint.json exists, no snapshot** → partial warm start (from auto-save) — use checkpoint, note it's from auto-checkpoint not a proper handoff
- **neither exists** → cold start

## Notes

- Checkpoint does NOT replace /handoff. It's a safety net, not a substitute.
- Checkpoint is overwritten each tick. No history — just the latest state.
- If /handoff runs, it writes snapshot.json. The checkpoint becomes irrelevant.
- The checkpoint file should be gitignored alongside snapshot.json.
