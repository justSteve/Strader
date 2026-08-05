---
name: tap-in
description: Initialize session with context briefing
context: fork
allowed-tools: Bash, Read, Write
---

# Tap In — Session Initialization

Read recent activity and current state to get oriented at session start.

## Workflow

### 1. Get Current Date

```bash
date +%Y-%m-%d
```

### 2. Check if Daily Housekeeping Needed

```bash
head -1 "${CLAUDE_PROJECT_DIR}/DaysActivity.md" 2>/dev/null
```

- If date doesn't match today or file missing: archive yesterday's file (if it exists) and create fresh one

```bash
PROJECT="${CLAUDE_PROJECT_DIR}"
TODAY=$(date +%Y-%m-%d)

# Archive yesterday's if it exists and has a different date
if [ -f "$PROJECT/DaysActivity.md" ]; then
  OLD_DATE=$(head -1 "$PROJECT/DaysActivity.md" | grep -oP '\d{4}-\d{2}-\d{2}')
  if [ -n "$OLD_DATE" ] && [ "$OLD_DATE" != "$TODAY" ]; then
    cp "$PROJECT/DaysActivity.md" "$PROJECT/archive/DaysActivity-${OLD_DATE}.md"
  fi
fi

# Create fresh file for today
cat > "$PROJECT/DaysActivity.md" << EOF
# DaysActivity - $TODAY
EOF
```

### 3. Read Recent Activity

```bash
head -80 "${CLAUDE_PROJECT_DIR}/DaysActivity.md"
```

Note open work items, recent state, continuity threads.

### 4. Read CurrentStatus.md

```bash
cat "${CLAUDE_PROJECT_DIR}/CurrentStatus.md" 2>/dev/null
```

### 4b. Observe the Surfaces (not just read about them)

```bash
bash "${CLAUDE_PROJECT_DIR}/scripts/surface_liveness.sh"
```

`CurrentStatus.md` above is a **claim** — what was true when someone last wrote
it. This is an **observation**. Where they disagree, the observation wins, and
the briefing should say so rather than quietly repeating the file.

> Added 2026-08-05 (st-42mn). Steve resubscribed GEXBot mid-afternoon; the
> session spent the rest of the day telling him "we have no GEX" while the
> collector was writing to the corpus in the next tmux window. Nothing was
> broken — the belief came from a memory file and a status line that were true
> when written. This is the same failure mode step 5's co-vf9q note describes:
> plausible, well-formed, wrong. A surface can change mid-session, and the
> operator should never have to remember to circle the agent in.

### 5. Check the Ready Queue (name-first)

The store is Dolt-backed (`.beads/embeddeddolt`). Read it through `bd`, and use
the ProperName view so items read by their human handle:

```bash
bd propername --ready 2>/dev/null | head -30
```

Each line is `PROPERNAME · st-id · P# · title` — carry the name, not just the id.

> Until 2026-07-21 this step read `tail -30 .beads/issues.jsonl`. That file is a
> **stale export**, last written 2026-06-12, not the live store — so every
> session from that date on oriented on a 5.5-week-old snapshot and had no signal
> anything was wrong. The export returned plausible, well-formed, wrong data,
> which is worse than returning nothing. Do not reintroduce a read of it
> (co-vf9q).

### 6. Output Session Briefing

Write to `${CLAUDE_PROJECT_DIR}/session-briefing.md`:

```markdown
## Session Briefing - YYYY-MM-DD HH:MM

### Recent Activity

**Last Session**: [timestamp] - [brief summary from most recent handoff]

**Open Work (carried forward)**:
- [item 1]
- [item 2]

### Current State

[Summary from CurrentStatus.md]

### Open Beads

| Bead | Status | Title | Type |
|------|--------|-------|------|
| id | status | title | type |

### Resumption Guidance

1. [specific next step]
2. [specific next step]

### Ready Status

[Ready to proceed | Issues require attention]
```

## Pairs With

- `/handoff` — Session end
- `/checkpoint` — Auto-save between handoffs

## Re-run Anytime

Invoke mid-session to refresh context:
```
/tap-in
```
