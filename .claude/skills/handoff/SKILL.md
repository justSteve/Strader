---
name: handoff
description: Prepend session handoff to DaysActivity.md
allowed-tools: Bash, Read, Write, Edit
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

4. **Check the ready queue (name-first)**
   The store is Dolt-backed (`.beads/embeddeddolt`). Read it through `bd`:
   ```bash
   bd propername --ready 2>/dev/null | head -30
   ```
   > Until 2026-07-21 this read `tail -30 .beads/issues.jsonl` — a stale export
   > last written 2026-06-12, not the live store. Do not reintroduce it (co-vf9q).

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

**Peer Digest (UNDELIVERED — COO inbox absent)** *(only when step 8b could not
deliver — carries the lines so the next session can)*:
- [what changed that COO needs]

---
```

6. **Prepend to DaysActivity.md**
   - Read existing content
   - Write: header + new entry + blank line + existing entries
   - Preserve the `# DaysActivity - YYYY-MM-DD` header at top

7. **Refresh CurrentStatus.md** *(only when standing state actually moved)*

   `CurrentStatus.md` is a standing operational snapshot, not a session log —
   what is wired up, live, or paused right now. Most sessions change nothing in
   it and it should be left alone. Update it when this session:

   - turned a data surface, cron, or instrument on, off, or broken
   - changed the risk posture, the execution gate, or a hard boundary
   - moved the phase (training → drills, sizing tier, live-date milestone)
   - resolved or added an item under **Attention Items**

   Rules: replace the stale line in place, never append a changelog. Bump
   **Last refreshed** to today with the authorizing bead. Do not restate
   session narrative — that is what the DaysActivity entry above is for.

   > This step exists because the file sat unmaintained from 2026-05-04 to
   > 2026-08-02: tap-in and handoff both read it, nothing wrote it [st-0ji].

8. **Close the peer channel** *(every handoff, no exceptions)*

   **8a. Pay any receipt this session owes.**

   ```bash
   python3 tools/a2a_inbox.py --open
   ```

   If this session read a peer memo and logged no reply, that is a protocol
   violation — write the reply **now, before the handoff completes**:

   1. Amend the memo file itself with a blockquote at the top:
      `> **UPDATE, YYYY-MM-DD:** ACK|SERVICED. <what happened, with evidence>`
   2. Append one line to the bottom of Strader's ledger,
      `docs/a2a/inbox.md`, under `## Ledger`:

   ```
   | YYYY-MM-DD HH:MM CT | Strader | ACK | st-<bead> | <memo filename without .md> | - | <what was understood and what happens next> |
   ```

   Get `REF` exactly right — it is the join key the tool matches on, and a
   wrong one leaves the memo OPEN forever. Append at the bottom; never edit or
   delete an existing line. Timestamp with
   `TZ=America/Chicago date '+%Y-%m-%d %H:%M CT'`.

   `ACK` — "received, understood, not doing it yet" — is a legitimate answer
   and takes thirty seconds. What is not acceptable is reading a memo and
   logging nothing.

   > **This receipt is the only thing a handoff writes into Strader's own
   > inbox** (`docs/a2a/receipt-protocol.md` §2: a memo *to* Strader and its
   > receipt both land in Strader's ledger). Strader's **own commits are not
   > peer events** — never log a Strader commit there, and never put the
   > digest below there.

   **8b. Write the peer-facing digest into COO's inbox.** Probe the target
   first — do not assume it exists:

   ```bash
   ls -l /root/projects/COO/docs/a2a/inbox.md
   ```

   Draft 3–5 lines of **"what changed that COO needs"** either way. Not a
   session summary — the filter is *would COO act differently for not knowing
   this?* Candidates: canon edits under `knowledge/**`, anything COO's
   conventions embed or point at, changed skills/rules/settings, a decision
   Steve made that binds both agents, a tool COO would otherwise rebuild. If
   genuinely nothing meets the bar, write one line saying so — an explicit
   "nothing COO needs this session" beats silence.

   - **Target exists** → append the lines at the bottom of COO's ledger,
     one event per line, never batched, never rewriting an existing row:

     ```
     | YYYY-MM-DD HH:MM CT | Strader | DIGEST | st-<bead> | <short SHA or -> | <paths or -> | <what changed that COO needs, ≤120 chars> |
     ```

     `REF` is the short SHA of the commit that carried that change (`git log
     --oneline` for this session), or `-` if it was not a commit. `DIGEST`
     lines are informational — they owe no receipt (receipt-protocol §1).

   - **Target missing** — the state as of 2026-08-13; COO's inbox is Phase 2
     item 5 on **COO's** side and has not shipped → **do not create it.**
     Strader writes only inside its own repo. The digest is then *undelivered*,
     and it must say so, visibly, in two places:

     1. In the handoff entry itself, as a block that carries the lines verbatim
        so the next session can deliver them:

        ```markdown
        **Peer Digest (UNDELIVERED — COO inbox absent)**:
        - [line 1]
        - [line 2]
        ```

     2. In the handoff message to Steve: one line —
        *"COO inbox absent at /root/projects/COO/docs/a2a/inbox.md; N digest
        lines parked in the DaysActivity entry."*

   Never skip the digest because the target is missing, and never let it fail
   quietly. Unannounced change is the failure this whole phase exists to end
   (`docs/plans/2026-08-12-zgent-sync-plan.md`, Phase 3 item 10, st-4ld0).

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
5. **Receipts paid** — `python3 tools/a2a_inbox.py --open` shows no memo this
   session read but did not answer
6. **Digest delivered or declared** — the DIGEST lines are in COO's inbox, or
   the entry carries a `**Peer Digest (UNDELIVERED — COO inbox absent)**` block
   and the handoff message says so

If any check fails, fix the entry before reporting success.

## Notes

- Entries are **prepended** (newest on top)
- Keep summaries concise and actionable
- Files changed section only if files were actually modified
- **Tried section**: Include when the session involved debugging or investigation. Failed approaches are the most expensive thing for the next session to rediscover.
