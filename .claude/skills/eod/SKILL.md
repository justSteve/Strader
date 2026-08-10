---
name: eod
description: Close the TRADING DAY — read the day's fact packet and write a Day Close entry to DaysActivity.md. Use at or after the cash close, or on any past trading day that has no Day Close entry. Distinct from /handoff, which closes a SESSION.
allowed-tools: Bash, Read, Write, Edit
---

# EOD — Trading Day Close

Write the **Day Close** entry for a trading day: what the tape did against the
plan, what the calls were worth, what data landed, and the one thing learned that
would otherwise survive only in a commit message.

## Why this is not /handoff

They close different things, and conflating them is the bug this skill exists to
fix [st-z92a].

| | `/handoff` | `/eod` |
|---|---|---|
| closes | a **session** — a stretch of your attention | a **trading day** — 08:30–15:00 CT |
| triggered by | Steve stopping | the market closing |
| answers | where do I resume, what did I try that failed | what did the market do, was the plan right |
| may span | one day, or two — sessions are allowed to cross midnight | never; a day is a day |
| owner | enterprise convention (COO) — do not restyle it here | Strader only. No other zgent has a trading day. |

A session that runs Monday 22:00 → Tuesday 02:00 produces **one** handoff and
touches **two** trading days. That is fine and expected. It is also why the day's
record cannot hang off the session.

On 2026-08-08 five commits landed, no handoff ran, and the day's one substantive
result — the round-4 scalp metrics retiring the two-signal for the singleton lane
— survived only inside a commit message. That is the failure. The packet now
makes the facts survive mechanically; this skill makes the reading survive.

## The packet comes first

A 15:15 CT cron writes `data/eod/<date>.md` — the day's facts, gathered, with no
conclusions in it. **Read it before writing anything.**

```bash
timeout 120 .venv/bin/python scripts/eod_packet.py --audit
```

That prints recent trading days and whether each has a packet and a Day Close.
Work the gaps oldest-first — a day goes cold fast.

If the packet is missing (cron failed, or you are closing a past day):

```bash
timeout 300 .venv/bin/python scripts/eod_packet.py --day YYYY-MM-DD
```

Exit 3 means the packet carries a **hard gap** — a stream collected nothing, or
GEX rows landed outside the collect window. Lead the entry with it; live tape
cannot be re-collected tomorrow.

## What you add that the packet cannot

The packet has facts. You have the read. Do not restate its tables — the entry
should be worth reading next to it, not instead of it.

1. **Plan vs. actual.** The morning Mancini levels and the regime read are on
   disk. Did price respect them? Name the level and what happened at it.
2. **Setups that appeared, and whether they were taken.** A V-dump-and-return
   that printed and was missed is worth more to record than one that was taken —
   it is the drill material.
3. **Calls, graded.** Hindsight measurement holds confirmation authority here,
   not Steve's chair-time impression and not yours. A call with no outcome yet is
   ungraded, and saying so is the honest entry.
4. **The one thing learned.** If nothing was learned, write that. A day that
   taught nothing is data about the method's coverage.
5. **What the day means for tomorrow** — one line, only if it actually does.

## Voice

Same as everywhere else: answer first, numbers with just enough context to read
them, no filler. `[ALERT]` prefix for anomalies. This entry is Steve-facing, so
the `convention` concepts in `knowledge/` govern — establish terms before
abbreviating them, no bare codes.

Do not manufacture significance. Most days are ordinary and the entry is short.

## Entry format

Prepend to `DaysActivity.md`, newest on top, following the existing conventions
in the `daysactivity-format` skill. The heading **must** contain the literal
words `Day Close` and the ISO date — `eod_packet.py --audit` matches on exactly
that, and an entry it cannot see counts as a day that was never closed.

```markdown
## HH:MM - Day Close [2026-08-10]

**Tape**: [what price did, in one or two sentences — the shape of the day]

**Plan vs. actual**: [the levels that mattered and what happened at them]

**Setups**: [what appeared; taken or missed; why]

**Calls**: [each call and its grade, or "none recorded"]

**Data**: [only if something is wrong or notably good — otherwise omit; the
packet already carries the full table]

**Learned**: [the one thing, or "nothing new"]

---
```

If the day being closed is **not** the day the live `DaysActivity.md` is headed
for — you are closing Friday on a Monday, or a session crossed midnight — put the
full ISO date in the heading as shown and say in the first line which day is
being closed. Do not re-roll or re-archive the file; that belongs to `/tap-in`.

## Commit

`data/` is gitignored, so the packet needs `-f` — the same convention
`data/calls/` and `data/measurement/` use.

```bash
git add -f data/eod/<date>.md data/eod/<date>.json
git add DaysActivity.md
```

Commit with the authorizing bead. Standing commit-and-push authority applies.

## Post-write check

1. The heading carries `Day Close` **and** the ISO date.
2. `scripts/eod_packet.py --audit` no longer reports that day as a gap.
3. Every hard gap in the packet is named in the entry.
4. Nothing in the entry restates a packet table verbatim.
