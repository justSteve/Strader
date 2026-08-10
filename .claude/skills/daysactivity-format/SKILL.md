---
name: daysactivity-format
description: DaysActivity.md formatting conventions. Use when writing handoff entries or any content destined for DaysActivity.md.
user-invocable: false
---

# DaysActivity.md Format

## Purpose

`DaysActivity.md` is a cumulative daily log that captures session activity in reverse chronological order (newest on top).

## File Location

`${CLAUDE_PROJECT_DIR}/DaysActivity.md`

## Structure

```markdown
# DaysActivity - YYYY-MM-DD

## HH:MM - [Entry Type]
[Content...]

## HH:MM - [Entry Type]
[Content...]
```

## Entry Types

### Session Handoff
```markdown
## 14:30 - Session Handoff

**Summary**: [What was accomplished]

**Open Work**:
- [Item 1]
- [Item 2]
```

### Manual Note
```markdown
## 15:45 - Note

[Free-form content]
```

## Formatting Rules

1. **Single-line summaries** stand alone as complete thoughts
2. **File listings** get their own lines (one file per line)
3. **Timestamps** use 24-hour format (HH:MM)
4. **Newest entries** always at top (prepend, don't append)

## Daily Lifecycle

1. **Session start**: `/tap-in` archives yesterday's file, creates fresh one if needed
2. **Throughout day**: Entries prepended via `/handoff`
3. **End of day**: Final `/handoff` captures session state
