# Zgent Sync Plan — one shared understanding for Strader and COO

> **STATUS 2026-08-14 — RATIFIED AND LARGELY EXECUTED.** Landed since ratification: Phase 0 doctrine reconciliation (st-zc38), the entitlements registry (st-g0or), this repo's A2A ledger and receipt protocol (st-75z0), and COO's standing write authority written into `.claude/rules/zgent-permissions.md` with both gates. The ledger is in daily use — two peer commits were caught and repaired against it today (st-s8ng).


*st-aski · 2026-08-12 · Strader, from a 24-agent review of all 38 Strader + COO
session transcripts 2026-08-02 → 08-12 plus both agents' full persistent-context
surfaces. Companion memo to COO: `docs/a2a/2026-08-12-strader-to-coo-zgent-sync-plan.md`.*

---

> ## RATIFIED — Steve, 2026-08-13
>
> Approved for implementation. How the four decisions resolved:
>
> | # | Decision | Resolution |
> |---|---|---|
> | 1 | COO's standing push-to-Strader authority | **Ratified with the gate.** COO holds standing authority to commit into Strader; every such write must read the owner's canon first and announce itself with an `docs/a2a/inbox.md` line in the same commit. `.claude/rules/zgent-permissions.md` rewritten to match — st-75z0. |
> | 2 | Strategy 3 vs the singleton directive | **Rewrite, not removal — deferred to the next session** (Steve, 08-13: *"rewrite existing strat at next session"*). CLAUDE.md deliberately untouched on 08-13. Filed as **st-mfpm**; the doctrine content goes to Steve for review before it lands. |
> | 3 | Contract home | **Proposal stands.** Canonical in COO `conventions/`, verbatim embed in both CLAUDE.mds, tap-in drift check. |
> | 4 | Ratify this plan | **Yes.** This plan is the delegation authority for COO's half, per its own rules. |
>
> Implementation began 08-13 with a four-way subagent fan-out across st-zc38,
> st-g0or, st-75z0, st-pfrz; st-4ld0 (the ritual layer) sequenced after, because
> three of the others land files its skill steps must read.

---

**The short version.** The transcripts show one failure shape behind nearly every
incident of the last ten days: knowledge lands in whichever repo the conversation
happened in, neither agent's session rituals read the other's surfaces, and you are
the only routing layer between us. The fix is not a cleaner designer/implementer
split — the record shows that split collapsed within hours of being declared and
was never going to hold. The fix is **mutual visibility built as mechanism**: one
canonical home per fact with loaded pointers in both repos, session rituals that
read the peer's state, channels that announce and acknowledge, and observation
probes replacing written claims. Five design laws, four phases, four decisions
that are yours. Phase 0 is already done as of this morning.

---

## What the review found

Ten days, five patterns, evidence attached:

1. **Corrections bind only the repo they were spoken in.** Your fly doctrine was
   fixed at source in Strader on 08-05 (banned-framing block, four prior
   corrections cited) — and COO priced ATM/theta flies during your live 08-11
   trade anyway, because COO's context never carried any of it: its CLAUDE.md
   contained the words *butterfly, fly, flies* zero times while months of fly
   conversations happened in its sessions. You re-taught your own method six-plus
   times. The 08-08 singleton redirect ran the same route in reverse: delivered to
   COO, duplicated into COO memory, while Strader's CLAUDE.md still carries the
   contradicted Strategy 3 today.

2. **Subscription and entitlement state flowed only through you, four times.**
   Databento OPRA→Futures (only your billing-portal view caught it), the GexBot
   resub (a morning of "no GEX" while the collector ran in the next tmux window),
   the State→Quant tier reveal (a night of 1DTE + orderflow legs silently
   uncollected — "We should have been working all night"), and the OPRA
   cancellation both agents were still assuming active on 08-11. Until this
   morning my own knowledge bundle *still* asserted the cancelled OPRA sub as
   "Live data: Active."

3. **COO operates my repo invisibly.** Under a standing authorization recorded
   only in COO's memory (2026-07-01), COO files/claims/closes st-prefixed beads,
   pushes to my master, and has edited my CLAUDE.md, settings.json, skills,
   auto-memory, and Schwab reauth script — each time noting my live session
   wouldn't see it, sending no message. I learned bd writes were repaired
   estate-wide only from this review. The written rules say the opposite
   ("cross-repo writes require explicit delegation via beads"); reality runs on a
   remembered verbal grant plus a remembered verbal exception, neither visible to
   me. One prior incident blind-staged my settings.json into a schwab-gate
   violation.

4. **The read half of our knowledge layer fails.** The write half works — 24
   typed concepts in my bundle, ~100 conventions in COO's, a working graduation
   flow. But four COO measurement rounds ran in my repo without reading the
   concept that answered their question (channel-family-taxonomy: clock, AUC
   .875, "the concept had named it five days ago and nobody read it"), and COO
   built a flush watcher from scratch with invented thresholds while my
   footprint recognizer already emitted flush recognitions — you were the one
   who pointed that out.

5. **Every channel is silent, slow, or lying.** gc mail: dead in both
   directions, failed silently for weeks. A2A file memos: the only working
   two-way channel, but no bell, no receipt — my 07-29 desk-migration request
   sat until you personally re-delivered it to COO on 08-04; a flashcard
   question blocked 19 days. Claim surfaces (CurrentStatus, briefings, session
   reviews) repeatedly asserted things false at read time — the RTH-only line
   alone consumed a build-revert-restore cycle and three of your interventions.

The cost curve in your own words runs from "i'm relying on my own prompting
skills" (08-04) through "That's on me" (08-07, the lost Quant night), "I have not
adaquately engineered your context" (08-09), "i'm feeling swamped" (08-10), to
"we need structural changes" (08-11). This plan is the structural change.

---

## Five design laws

Each is proved by a specific failure above; each shapes what follows.

1. **Loaded beats retrieved.** A fact in an always-loaded surface changes
   behavior; a fact in a retrievable file does not (fly doctrine, Strategy 3).
2. **One home per fact; pointers, never mirrors.** The 08-12 fly-doctrine
   duplication drifted *the same day* it was created. Mirrored prose always
   diverges; a loaded pointer to one canonical home cannot.
3. **Observation beats claim.** Every stale-state incident traces to trusting a
   written claim. My tap-in's liveness probe (st-42mn: "CurrentStatus is a
   claim, the probe is an observation, observation wins") is the pattern —
   extended to everything either of us asserts about the other.
4. **Channels need bells and receipts.** A mailbox nobody polls and a commit
   nobody announces are how requests sit 19 days and security surfaces change
   silently.
5. **Mechanism over exhortation.** "Consult the bundle" failed four times as a
   norm. Every fix below is a numbered skill step, a probed file, or a diff
   check — not a rule asking agents to remember.
6. **When copies disagree, canon wins — not the newer one.** *(Added 2026-08-13,
   from the st-zc38 backport.)* COO's fly rule was written 08-12 from a live
   incident, with high confidence, and it over-broadened against canon four
   months older — flatly banning the pin runner Steve has documented since
   2026-04-26. The newer document was the wrong one. Recency feels authoritative
   in the moment precisely because the incident is vivid, so the tie-break has to
   be structural: **the single home wins on its own subject, regardless of
   timestamps**, and a peer who thinks canon is wrong raises it rather than
   overwriting it. Both agents proved this works on 08-13 — COO verified the
   conflict against two commit hashes, took it to Steve, and changed its copies
   rather than arguing from recency.
7. **Being right is not being the authorizer.** *(Added 2026-08-13, from COO's
   refusal.)* COO declined to widen its own write scope on Strader's say-so even
   though Strader was substantively correct and acting in good faith — the
   ratification existed only in a peer message and an uncommitted working tree.
   A peer cannot widen a peer's write scope, and evidence has to be in history to
   be checkable. Both agents hold this in both directions.

---

## The plan

### Phase 0 — stop the bleeding *(done this morning, remainder this week)*

| Item | Status |
|---|---|
| Fix `knowledge/databento-live-collection.md` (cancelled OPRA still "Active") | **Done**, st-onr4 closed |
| Fix CurrentStatus stale items (bd-BLOCKED, method-notes) | **Done** |
| Close st-p3lv (was waiting on the bd repair) | **Done** |
| Backport COO's newer fly specifics (X±12 centers, expiry ban, orderflow-helps-flies, 08-11 verbatim quotes) into `knowledge/directional-gex-butterflies.md` so canon is current again | **st-zc38**, today |
| Reconcile the GexBot record (one timeline; COO's stale "orderflow entitlement missing" header; retire `gexbot-paused-orderflow-focus.md` title) | COO side — in the A2A memo |
| **Your call:** Strategy 3 in my CLAUDE.md vs the singleton directive (co-0a3oj has sat since 08-09) | Decision 2 below |

### Phase 1 — the shared spine *(week of 08-17)*

1. **One enterprise contract, loaded by both.** A single division-of-labor
   document — the authority split, every standing authorization, every active
   exception *with expiry dates* — canonical in COO's conventions (structural
   authority), embedded verbatim in both CLAUDE.mds, with a tap-in diff check
   that flags drift between the embed and canon. Today the contract exists only
   in my repo and its exceptions exist only in COO's memory: we load different
   constitutions.
2. **Single-home rule.** Trading doctrine and operator profile: canonical in
   Strader `knowledge/`. Structural conventions, factory patterns, desk
   machinery: canonical in COO `conventions/`. The other repo carries a loaded
   *pointer* (one CLAUDE.md line naming the canonical path plus the one-sentence
   gate). The fly-doctrine mirror (co-tvv3u's manual drift-check) is the test
   case: replace it with a mechanical diff at tap-in.
3. **A corrections ledger.** Any durable correction you issue, in either
   session, lands in its canonical home *the same turn* plus one line in a
   shared ledger both tap-ins read. Your behavioral corrections — no deadline
   nagging, act on cheap reversible actions, response volume, enumerate before
   measuring — consolidate into one shared conduct concept binding both agents,
   so you never pay the same lesson twice again.
4. **An entitlements registry.** One file: Databento plan, GexBot tier and
   entitlements, Schwab token state, OPRA status. Probed by both tap-ins
   (liveness-checked where probeable, dated where not), pointed at by bundle
   docs — never restated in them. Four of the costliest incidents were
   subscription gaps only you could close.

### Phase 2 — honest channels *(weeks of 08-17 and 08-24)*

5. **Peer inbox with mandatory announce.** Any commit by either agent into the
   other's repo appends one line to the target's `docs/a2a/inbox.md` — absolute
   requirement for CLAUDE.md, `.claude/`, settings, skills, and
   schwab-adjacent files. The target's tap-in reads the inbox. Silent edits to
   a peer's instruction or security surface end.
6. **A2A bell and receipt.** Every memo gets an ack-or-serviced reply within
   one session of the recipient's next tap-in (the pattern COO's Anki
   "SERVICED" commit already proved). Memos unanswered past 3 sessions surface
   in the recipient's briefing. gc mail gets a loud stub in my repo — a call
   errors with "use docs/a2a/" instead of silently going nowhere.
7. **Bead visibility.** My tap-in surfaces st-beads filed/claimed/closed by COO
   since my last session, and co-beads that cite st-work (killing the "fix per
   hvxye" grep hunt). Peer-prefix bead actions carry a one-line who/why note,
   turning silent occupation into legible delegation.
8. **Shared liveness probe.** Extend my `surface_liveness.sh` into a probe
   covering both agents' collectors, supervisors, and desk windows, publishing
   one observations file both tap-ins read. Neither agent ever again asserts
   the other's process state from a relayed claim.

### Phase 3 — shared rituals *(week of 08-24, then standing)*

9. **Peer-sync tap-in step, both repos:** read the peer's CurrentStatus, the
   inbox, the shared current-focus, and `git log` of the peer's
   knowledge/conventions since last session. Cheap — seconds — and it ends
   cold starts that know nothing of the other half.
10. **Peer-facing handoff digest:** every handoff writes 3–5 lines of "what
    changed that the other agent needs" to the peer's inbox. This is the
    minimum viable version of "know what the other is doing," and it costs one
    paragraph per session.
11. **One lifecycle template.** tap-in/handoff/daysactivity factor into a COO
    factory template with per-repo hooks, so a fix to the ritual propagates to
    both instead of forking (my liveness probe and CurrentStatus writer-role
    fixes port to COO's copies, which independently filed the same failure
    class as P1).

---

## The division of labor, restated

The review scored the old split: COO crossed the written boundary on all seven of
its digested days — usually with your verbal cover — while I stayed in-repo
almost completely. One-directional erosion means the written contract described
neither agent's actual behavior. So the restatement is not a thicker wall:

- **Authority is about who decides, not who types.** Strader decides what market
  data means, what the doctrine is, whether an abstraction fits the domain. COO
  decides how things are structured, what the conventions are, how the factory
  works. Unchanged.
- **Either agent may build anywhere** — but a build in the peer's territory
  *reads the owner's canon first* (checkable gate, not a norm) and *announces
  itself* (inbox line, same commit).
- **Exceptions are written, dated, and loaded by both** — never remembered
  verbally by one.

## Decisions that are yours

1. **COO's standing push-to-Strader authority.** Ratify it (then both
   zgent-permissions rules get rewritten to match reality, plus the
   read-canon-first gate and mandatory announce) — or retire it (COO proposes,
   I apply in-repo). The current state — rule says no, memory says yes — is the
   worst of both. *My read: ratify with the gate; the bandwidth is real and the
   silence, not the writing, is what burned us.*
2. **Strategy 3 (range scalping) vs your singleton directive.** My always-loaded
   CLAUDE.md still teaches 3–5-point range scalps. If singletons-as-futures-proxy
   is the standing intent, Strategy 3 comes out or gets rewritten. Trading
   judgment — yours.
3. **Contract home.** Proposal: COO `conventions/` as canon, verbatim embed in
   both CLAUDE.mds, tap-in drift check. Say the word and it stands elsewhere.
4. **Ratify this plan.** COO's half (contract doc, lifecycle template, GexBot
   record, inbox convention, its tap-in changes) goes to COO via the A2A memo
   the moment you approve — with this plan as delegation authority, per its own
   rules.

## What success looks like

Rerun this exact 10-day transcript review in mid-September. Targets: zero
instances of you carrying operational state between us (was: continuous), zero
silent cross-repo edits (was: ~15 commits), zero stale-subscription incidents
(was: 4), every correction visible in both repos the day it lands (was: months),
A2A round-trip inside one session-pair (was: 19 days / never). If those counts
aren't near zero, the mechanisms — not your prompting — get redesigned again.

## Strader-side beads filed today

- **st-zc38** — backport COO's fly-doctrine additions into the canonical bundle concept
- **st-g0or** — entitlements registry: probed file, tap-in wiring, bundle pointers
- **st-4ld0** — tap-in peer-sync step + handoff peer digest (Phase 3, items 9–10)
- **st-75z0** — gc-mail loud stub; inbox.md + receipt protocol, Strader side
- **st-pfrz** — live-monitoring surfaces registry (six overlapping tools, one authority table)

COO-side work is enumerated in the companion A2A memo and beads in COO's own
tracker on your ratification.
