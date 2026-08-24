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

### 4c. Read the Peer Channel (inbox, receipts, malformed rows)

```bash
python3 tools/a2a_inbox.py
```

With no argument the cutoff is the **last session handoff**, so this answers
"what happened here while I was away." Three blocks come back and each has a
different job — do all three, in order:

1. **`LANDED SINCE …`** — paste it **verbatim** into the briefing under a
   **Peer Activity** heading. Then check the `COMMIT` lines' paths: if any
   touches `CLAUDE.md`, `.claude/**` (rules, hooks, skills, settings, state),
   a schwab-adjacent path (`broker_schwab/**`, `scripts/run.sh`, anything
   matching `*schwab*`, anything under `tokens/`), or `knowledge/**`, raise it
   in the briefing's **first** section — above the bead queue. An instruction
   or security surface moved underneath this session, and that outranks
   whatever was queued. One unannounced peer commit blind-staged
   `settings.json` into a schwab-gate violation; that is the class of event
   this step catches.
2. **Both `RECEIPTS` blocks** — paste both into Peer Activity. Any `[ALERT]`
   line is a **STALE** memo (open 3+ handoffs) and becomes **Resumption
   Guidance item 1**, not just printed text. A stale memo is session-open work:
   answer it before starting anything new. The reply costs one line — see
   `docs/a2a/receipt-protocol.md` §2, and `ACK` ("received, not doing it yet")
   is a legitimate answer.
3. **A trailing `[ALERT] inbox.md has N malformed line(s)`** — if it appears,
   surface it in the briefing too. Those rows are **not counted** in the blocks
   above, so a malformed row is a peer event nobody sees. Fix the row in
   `docs/a2a/inbox.md` (format is in that file's header) as session work.

`OPEN` and `STALE` are **computed by the tool** (`tools/a2a_inbox.py`, spec in
receipt-protocol §3). Do not eyeball `docs/a2a/inbox.md` and judge staleness
yourself, and do not reimplement the counting anywhere — one home per fact
applies to code too.

### 4c-bridge. Poll the zgent-bridge file-drop

The a2a ledger above is the in-repo channel COO and Strader both read every
session. The **zgent-bridge** (`/mnt/c/Users/steve/zgent-bridge/{co,st,cd}/inbox/`)
is a separate Windows-side file-drop that no WSL estate used to poll at start —
so a message dropped there sat until Steve relayed "check the bridge". Added
here 2026-08-24 (COO co-ur0fv) so it surfaces on its own:

```bash
bash /root/projects/COO/factory/scripts/bridge-check.sh
```

The **`st/ Strader … N unread`** line is Strader's own inbound. If `N > 0`,
surface each named file in the briefing under Peer Activity and read it — it is
a message (usually from COO) waiting on Strader. Routing note: COO↔Strader
traffic belongs in the a2a ledger above; a COO→Strader message that arrives
here instead is a routing mistake, so answer its substance and tell COO to land
future ones as a ledger row. The `co/` and `cd/` lines are not Strader's to act
on. Read-only; non-fatal if the script or the mount is absent.

### 4d. Probe the Entitlements Registry

```bash
/root/projects/Strader/.venv/bin/python3 /root/projects/Strader/scripts/entitlements_probe.py
```

Print the output. It has three sections and they are not equivalent:

- **OBSERVED** — measured from local state files just now. A green line proves
  **data is landing**, never that the bill is paid.
- **DATED** — what Steve reported from a billing portal on the date shown,
  unverified since. Quote these *with* their date ("as of 2026-08-04, Steve
  reported …"), never as current truth.
- **NEEDS STEVE** — facts no probe can settle. Anything here that this session
  actually depends on goes into the briefing's first section.

**Exit code:** `1` means something needs a human *today* — a probe alarmed, or a
dated fact aged out / hit its review date. `2` means the probe itself failed
(missing or unparseable registry) — say that out loud rather than reporting "no
entitlements." **`0` does not mean NEEDS STEVE is empty:** standing
never-confirmed entries (TradingView, LuxAlgo, Mancini, Schwab data rights)
print every run without flipping the code, by design — a check that always
fails is a check nobody reads. So read the block, not only the code.

This probe reads **local files only** — no vendor API, no credentials, nothing
the Schwab gate covers (`.claude/rules/schwab-api-gate.md`). It is safe to run
at any point in a session.

### 4e. Read the Peer's State (COO)

```bash
head -40 /root/projects/COO/CurrentStatus.md
```

```bash
git -C /root/projects/COO log -10 --date=format:'%Y-%m-%d %H:%M' --pretty='%ad  %h  %s' -- conventions/
```

`CurrentStatus.md` is COO's **claim** about itself, and it can be weeks stale —
read it for standing posture, not for what is true right now. The `git log` is
the **observation**. Everything dated at or after the `LANDED SINCE` cutoff
printed in 4c is new since our last session.

Conventions are canonical in COO's repo under the single-home rule (structural
conventions, factory patterns, desk machinery). If one of those commits touches
something this repo embeds or points at, read the convention before trusting
the local copy — **when copies disagree, canon wins on its own subject,
regardless of which is newer** (sync-plan design law 6).

Both commands are read-only. Tap-in never writes into COO's repo.

> Why a fixed `-10` rather than `--since=<cutoff>`: git accepts an unparseable
> date **silently** and prints nothing, which reads exactly like "COO changed
> nothing" (verified 2026-08-13). A count-limited log with visible dates cannot
> fail that way.
>
> Plan item 9 also names a "shared current-focus" surface. No such file exists
> in either repo as of 2026-08-13 — the step is deliberately absent, not
> forgotten. Add it here when the surface ships; do not invent a substitute.

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

### [ALERT] Moved Underneath Us

*Include this section ONLY when there is something in it — and when there is,
it goes first, above everything else. Sources: a 4c COMMIT touching a
required-announce class, a 4d exit 1 or a NEEDS STEVE item this session
depends on, a 4b observation that contradicts CurrentStatus.md.*

- [what moved, who moved it, what it means for today]

### Recent Activity

**Last Session**: [timestamp] - [brief summary from most recent handoff]

**Open Work (carried forward)**:
- [item 1]
- [item 2]

### Peer Activity

[LANDED SINCE block from 4c — verbatim]

[RECEIPTS OWED BY STRADER block — verbatim]

[RECEIPTS AWAITED FROM PEERS block — verbatim]

[malformed-line report from 4c, if the tool printed one]

**COO**: [one line of standing posture from CurrentStatus.md, dated] ·
[conventions commits newer than the cutoff, or "no conventions changes"]

### Entitlements

[probe verdict: exit code + any OBSERVED line that is not OK + the NEEDS STEVE
items that bear on today. Omit the standing never-confirmed list unless it
bites today.]

### Current State

[Summary from CurrentStatus.md]

### Open Beads

| Bead | Status | Title | Type |
|------|--------|-------|------|
| id | status | title | type |

### Resumption Guidance

1. [any [ALERT] receipt from 4c — answering it IS item 1]
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
