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

### Day Close *(Strader only — written by `/eod`)*
```markdown
## 15:30 - Day Close [2026-08-10]

**Tape**: [the shape of the day]
**Plan vs. actual**: [levels that mattered, what happened at them]
**Setups**: [appeared; taken or missed]
**Calls**: [each call and its grade]
**Learned**: [the one thing, or "nothing new"]
```

The heading must carry the literal words `Day Close` **and** the ISO date —
`scripts/eod_packet.py --audit` matches on exactly that, and an entry it cannot
see counts as a day that was never closed. See the `eod` skill.

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
5. **Cross-midnight entries** carry the full date: when an entry's own date
   differs from the file's header — a session that ran past midnight, or a day
   being closed after the fact — write `## 2026-08-11 02:00 - ...` instead of a
   bare `## 02:00 - ...`. Otherwise a 02:00 entry sitting above a 22:00 entry
   reads as out of order rather than as the next day. [st-z92a]

## Daily Lifecycle

1. **Session start**: `/tap-in` archives yesterday's file, creates fresh one if needed
2. **Throughout day**: Entries prepended via `/handoff`
3. **Cash close (Strader)**: a 15:15 CT cron gathers the day's facts into
   `data/eod/<date>.md`; `/eod` reads that packet and writes the **Day Close**
   entry. This runs on the trading day's clock, not the session's.
4. **Session end**: `/handoff` captures session state

Steps 3 and 4 are independent. A session may span two trading days and produce
one handoff; a trading day may end with no session running and still get closed.
Neither substitutes for the other. [st-z92a]

> **Only `/tap-in` rolls and archives the file.** `/eod` never re-rolls it —
> closing Friday on a Monday writes a dated entry into Monday's file, which is
> why rule 5 exists.
