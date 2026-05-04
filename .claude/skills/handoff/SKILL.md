---
name: handoff
description: Prepend session handoff to DaysActivity.md
allowed-tools: Bash, Read, Write
---

# Create Session Handoff

Prepend a session handoff entry to `DaysActivity.md` (cumulative daily log).

## Anti-Shadowing Rule

NEVER generate DaysActivity entries freeform. Only this skill writes to DaysActivity.md. Freeform summaries skip bead-status checks, timestamp formatting, and validation. If you need to record session state outside of this skill, use `bd remember` or `bd comment`.

## Workflow

1. **Get current date and time**
   ```bash
   date +%Y-%m-%d
   date +%H:%M
   ```

2. **Check if DaysActivity.md exists for today**
   ```bash
   head -1 "${CLAUDE_PROJECT_DIR}/DaysActivity.md" 2>/dev/null
   ```
   - If missing or wrong date: Create fresh file with today's header
   - If exists with today's date: Prepend new entry

3. **Gather context**
   - Read `CurrentStatus.md` for current state
   - Review recent conversation for session summary
   - Note any discoveries or issues encountered

4. **Check open beads**
   ```bash
   tail -30 "${CLAUDE_PROJECT_DIR}/.beads/issues.jsonl" | jq -r 'select(.status == "open" or .status == "in_progress") | [.id, .type, .title] | @tsv' | column -t
   ```

5. **Create handoff entry**

```markdown
## HH:MM - Session Handoff [Brief Topic Tag]

**Summary**: [1-2 sentence description of what was accomplished]

**Open Work**:
- [In-progress item 1]
- [In-progress item 2]

**Tried** *(include only for debugging/investigation sessions)*:
- [Approach 1] → [result — why it worked or didn't]
- [Approach 2] → [result — why it worked or didn't]

**Files Changed**:
path/to/file1.md
path/to/file2.ts

---
```

6. **Prepend to DaysActivity.md**
   - Read existing content
   - Write: header + new entry + blank line + existing entries
   - Preserve the `# DaysActivity - YYYY-MM-DD` header at top

## Entry Format Rules

- **Timestamp**: 24-hour format (HH:MM)
- **Summary**: Standalone sentence, no bullet
- **Files Changed**: One file per line, no bullets, relative paths
- **Separator**: `---` between entries

## Creating Fresh DaysActivity.md

If file doesn't exist or has wrong date:

```markdown
# DaysActivity - YYYY-MM-DD

## HH:MM - Session Handoff

[Entry content...]

---
```

## Post-Write Validation

After writing the entry, verify before reporting success:

1. **Timestamp present** — entry has `## HH:MM` header in 24-hour format
2. **Summary present** — `**Summary**:` line is a complete sentence
3. **Open work present** — if any beads are in-progress, `**Open Work**:` lists them
4. **Files listed** — if code was changed this session, `**Files Changed**:` is populated

If any check fails, fix the entry before reporting success.

## Notes

- Entries are **prepended** (newest on top)
- Keep summaries concise and actionable
- Files changed section only if files were actually modified
- **Tried section**: Include when the session involved debugging or investigation. Failed approaches are the most expensive thing for the next session to rediscover.
