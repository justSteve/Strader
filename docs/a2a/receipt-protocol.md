# A2A Receipt Protocol — every memo gets an answer, and silence becomes visible

*Authorizing bead st-75z0 · Phase 2 item 6 of `docs/plans/2026-08-12-zgent-sync-plan.md`
(st-aski) · companion to `docs/a2a/inbox.md`, which is where every event below is
logged.*

**The failure this replaces.** File memos are the only working two-way channel between
Strader and COO — and they have no bell and no receipt. A 07-29 desk-migration request
sat until Steve personally re-delivered it on 08-04. A flashcard question blocked 19
days. `gc mail` was dead in both directions for weeks and said nothing. The channel was
never the problem; the *absence of an answer* was, and nothing made that absence
visible to anyone but Steve.

**Design law behind it:** channels need bells and receipts, and mechanism beats
exhortation. "Remember to reply" already failed. So: a reply is a logged event, and an
unanswered memo is computed and printed into the briefing whether anyone remembers or
not.

## 1. The obligation

**Every memo gets an ack-or-serviced reply within one session of the recipient's next
tap-in.** Not the next convenient session — the next one. The reply is one of:

| Reply | Means | When to use it |
|---|---|---|
| `ACK` | Received, understood, not doing it yet | The ask needs work you cannot finish this session, or it needs Steve first |
| `SERVICED` | The ask is done | The work landed this session |

An `ACK` is not a stall — it is the honest answer most of the time, and it is what
converts nine days of silence into a known-open item. What is *not* acceptable is
reading a memo and logging nothing.

`DIGEST` lines (a peer's handoff summary) owe no reply. `WRITE`, `FILED` and
`STATUS` lines owe no reply — their announce *is* the receipt.

### The KIND vocabulary

Reconciled with COO 2026-08-13 [st-qfsz], after four correctly-announced peer rows
parsed as malformed because this ledger had no word for events
`.claude/rules/scope-and-permissions.md` (formerly `zgent-permissions.md`) already *requires* a peer to announce. They
became invisible to every tool that reads parsed events, on the day one of them
was reporting a live risk to the corpus. A vocabulary narrower than the
obligations it records does not enforce anything — it loses rows.

| KIND | Means | Owes a reply? |
|---|---|---|
| `WRITE` | A peer wrote into this repo — the same-commit announce obligation | No |
| `FILED` | A peer filed a bead here | No |
| `STATUS` | A peer reporting a state change on shared infrastructure | No |
| `MEMO` | FYI / an ask | **Yes** — `ACK` or `SERVICED` |
| `ACK` | Read and understood, not doing it yet | — |
| `SERVICED` | The ask is done | — |
| `DIGEST` | A peer's handoff summary | No |
| `DIRECTIVE` | An order relayed from Steve | No — authority is the author's, not the content's |

**`COMMIT` is retired**, in favour of `WRITE` (COO's ruling, 2026-08-13). One word
per event, and `WRITE` is the word `zgent-permissions.md` itself uses, so the
permission rule and the ledger now say the same thing. `COMMIT` still *parses*, so
the historical rows below remain valid history — retiring a word must not rewrite
the past — but a `COMMIT` row dated on or after the ruling is flagged as a problem
by `tools/a2a_inbox.py`, which turns the ledger test red. That test is the
enforcement; there is no separate discipline to remember.

## 2. How to reply

The pattern is COO's 2026-08-11 Anki memo, which is the working example in this repo:

1. **Write the update into the memo file itself**, at the top, as a blockquote:

   ```markdown
   > **UPDATE, 2026-08-13:** SERVICED. <what happened, with the verifying evidence —
   > "39/39 cards, 0 duplicates", not "done">. §0 below stands as the record.
   ```

   Amend the memo in place; do not create a reply file for a one-line answer. A reply
   that needs its own argument gets its own memo, and *that* memo gets its own `MEMO`
   line and its own clock.

2. **Append the receipt line to the inbox** — the recipient's `docs/a2a/inbox.md`,
   in the same commit as the update:

   ```
   | 2026-08-13 14:02 CT | Strader | ACK | st-4ld0 | 2026-08-11-coo-to-strader-anki-pipeline-state | - | Read; import path confirmed, no COO action needed for future deck imports |
   ```

   `REF` is the **original memo's** filename without `.md` — that is what links the
   receipt to the memo. Get it wrong and the memo stays open forever.

3. **Do not delete or rewrite the original claim.** COO's Anki memo kept its "NOT
   SERVICED — nine days lost, that failure is COO's" section under the SERVICED
   header. The record of the lapse is the point.

### Where the line goes

The inbox line always lands in the **repo that owns the inbox being read**. Concretely,
until COO ships its side (memo item 2):

- A memo **to** Strader, and Strader's receipt for it → `Strader/docs/a2a/inbox.md`.
- A memo **from** Strader → logged in `Strader/docs/a2a/inbox.md` too (so we can see
  when a peer has gone quiet on us), and once COO's inbox exists, also appended there
  by the sender — that is the peer's bell.

## 3. Staleness — the part that must be mechanical

> **Definition.** A memo is **OPEN** if the ledger holds a `MEMO` line whose `REF` has
> no later `ACK` or `SERVICED` line with the same `REF`.
>
> A memo is **STALE** if it is OPEN and **3 or more session handoffs** have been
> written since its `WHEN` timestamp.

"Session" is counted as a **handoff entry** — one `## HH:MM - Session Handoff` heading
in `DaysActivity.md` or `archive/DaysActivity-YYYY-MM-DD.md`, dated after the memo.
Handoffs are the only durable, per-session, timestamped artifact this repo writes, so
they are the session clock. Nothing new needs to be maintained for the count to work.

Both computations — OPEN and STALE — are implemented in `tools/a2a_inbox.py`. Do not
reimplement them in a skill; call the tool.

```bash
python3 tools/a2a_inbox.py                    # landed-since + open receipts (briefing default)
python3 tools/a2a_inbox.py --since 2026-08-10 # explicit cutoff instead of last handoff
python3 tools/a2a_inbox.py --landed           # just the "what landed" section
python3 tools/a2a_inbox.py --open             # just the receipts owed / awaited
```

Output shape (this is what gets pasted into the briefing):

```
LANDED SINCE 2026-08-12 08:53 CT (2 events)
  2026-08-13 09:14 CT  COO  WRITE  co-3x9f  .claude/skills/handoff/SKILL.md
      Ports Strader's CurrentStatus-writer step into the shared lifecycle template

RECEIPTS OWED BY STRADER (1)
  [ALERT] 2026-08-11 coo-to-strader-anki-pipeline-state — OPEN 4 sessions

RECEIPTS AWAITED FROM PEERS (2)
  2026-08-12 strader-to-coo-zgent-sync-plan — OPEN 2 sessions (COO)
```

`[ALERT]` marks STALE. The prefix is the house alert convention and it is the whole
point of the mechanism: a stale memo cannot be read as ordinary text.

## 4. Wiring — what tap-in and handoff must do

These two skills are owned elsewhere (st-4ld0). This section is the spec they
implement; nothing here is optional, and nothing here is implemented in this bead.

**tap-in — new step, after the surface-liveness observation and before the briefing:**

1. Run `python3 tools/a2a_inbox.py`.
2. Put the `LANDED SINCE` block into the briefing under a **Peer Activity** heading,
   verbatim. If a landed `WRITE` touched a required-announce class (`CLAUDE.md`,
   `.claude/**`, settings, skills, schwab-adjacent, `knowledge/**`), say so in the
   briefing's first section — an instruction or security surface changed under us and
   that outranks the bead queue.
3. Put both `RECEIPTS` blocks into the briefing. Any `[ALERT]` line is **carried into
   the session's open work**, not just printed — a stale memo is work, and the session
   answers it before it starts new work.
4. If the tool reports a malformed line, surface that too. A ledger that silently
   drops rows is the failure this replaces.

**handoff — new step, at the end:**

1. If this session read a peer memo and did not reply, that is a protocol violation;
   write the `ACK` line before the handoff completes.
2. Write the peer digest: 3–5 lines of "what changed that the other agent needs" into
   the **peer's** `docs/a2a/inbox.md` as `DIGEST` lines (Phase 3, item 10) once COO's
   inbox exists.
3. The handoff writes **exactly one** kind of row to Strader's own inbox: an `ACK` or
   `SERVICED` receipt for an inbound peer memo (per §2, a memo *to* Strader and its
   receipt both land in Strader's ledger — that is the join key that makes the memo
   stop reading as OPEN). Nothing else. In particular the handoff never writes
   `WRITE` rows for Strader's own commits, and never writes `DIGEST` rows here —
   own commits are not peer events, and a digest is written to the *peer's* ledger,
   not this one.

   *Corrected 2026-08-13 (st-4ld0).* This item previously read "Nothing about the
   handoff writes to Strader's own inbox," which contradicted §2 and would have made
   every inbound memo permanently OPEN — the receipt would have had nowhere to land.
   The ban was always meant to cover self-announcement, not receipts.

## 5. When the protocol is inconvenient

It will be. A memo arrives mid-session during live trading, or the ask needs Steve.
Reply `ACK` in one line and move on — thirty seconds. The protocol never asks you to do
the work on someone else's schedule. It asks you to make the silence impossible.
