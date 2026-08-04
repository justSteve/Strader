# Fools Remote Arm — Scoping

**Epic:** Fools Remote Arm (st-863b) · 2026-08-04 · research-first kickoff
**Strategy of record:** *Run You Fools* (co-vzdsk, 2026-07-21) — the meltdown-day
playbook. Steve recalled it as "Trade You Fools"; the playbook and bead carry
the Gandalf name.

## The target picture

Today, Run You Fools only works if Steve is in the chair when the meltdown
starts. This project builds the arm that works when he isn't:

1. **Detect** — a live flush/meltdown detector integrated with the FD0 Watcher
   and the footprint window's feeds, implementing the playbook's "obvious
   line" as a checkable signal stack.
2. **Alert** — the trigger reaches Steve's phone in seconds, carrying enough
   context to act on (regime evidence, clock context, contested-direction
   flag), through Do-Not-Disturb if he's away from the desk.
3. **Execute** — Steve can fire a *staged* order from the phone. Staging is
   authored by the system; the fire decision is his alone, same as the desk.

## What already exists (found today, 2026-08-04)

| Piece | State |
|---|---|
| The playbook | `myDesk/reports/meltdown-day-run-you-fools-playbook.md` (COO repo) — draft, S2-vs-S4 regime question, long-premium execution, turnover cycle. Thresholds explicitly conventional, untuned. Graduation to Strader's bundle was already the noted path. |
| The Watcher | FD0 flush-down harness component (`docs/superpowers/specs/2026-08-02-fd0-flushdown-design.md`, st-apzt): watches live quotes/tape, raises CUT presumptions, renders a TOS ticket to the *desktop* clipboard. Replay-smoke discipline (7/22, 7/31 tapes) already in its checklist. |
| Live feeds | footprint window runs `corpus_stream_databento.py` (ES + MBP-1 live), `live_footprint_feed.py`, `drill_bridge.py`. |
| Phone channel | **ClaudeClaw — a Telegram relay** (`localhost:3141/api/chat/send`) already consumed best-effort by `schwab_token_health.py`. **Not deployed here**: no repo at `/root/projects/claudeclaw`, no `.env`. Where its code lives is R2's first question. |
| Broker surface | `broker_schwab/` has client + quote/chain readers. **No order module exists.** Token lifecycle (7-day wall) is a known fragility — it becomes an *execution* dependency in this project, not just a data one. |
| Execution gate | Standing ruling (st-5ey): Strader authors, **Steve alone executes**. The phone changes the location of the finger, not the rule. |

## The clipboard question, answered early

Sending a TOS string to the iPhone clipboard is *half* possible: an iOS
Shortcut (or Pushcut) can set the phone's clipboard from a webhook. The half
that fails is the destination — **TOS mobile has no order-string entry**, so a
pasted string executes nothing. Clipboard remains a desktop-TOS mechanism
(where FD0 already uses it). Phone execution has to go through the Schwab API
behind a staging surface. R3 verifies the API half against current docs and a
probe, not memory.

## Candidate execution architectures (R3 compares)

- **[A] Tailscale-private web page** served from this box. Detector stages a
  single ticket; the phone page shows it with FIRE + confirm; nothing
  public-facing, no third party in the order path. Most private, most moving
  parts we own.
- **[B] Telegram bot buttons** via ClaudeClaw — alert and action in one
  channel; Telegram sees button taps (not credentials). Least friction if
  ClaudeClaw deploys cleanly.
- **[C] iOS Shortcut → Tailscale endpoint** — no page to build; confirm UX is
  weakest.

Non-negotiable rails regardless of channel: hard size caps · single-ticket
staging only (no free-form orders from the phone) · two-step confirm ·
dead-man kill switch · append-only order journal · token-health gate before
any staging.

## Research lanes (all beads under st-863b)

| Lane | Bead | Question it closes |
|---|---|---|
| R1 Flush Detector Live | st-g3yh | What can the Watcher detect live, from which channels, emitting what alert schema? |
| R2 Alert Channel | st-mk56 | ClaudeClaw's deploy path + Telegram vs Pushover (critical alerts) vs ntfy — primary + fallback verdict with latency tests |
| R3 Phone Execution Path | st-1tgh | Schwab order API entitlement/scope/format + architecture A/B/C verdict + paper-pilot design |
| R4 Obvious Line Formalization | st-rtuu | The playbook's line as a measured, decision-aligned, replay-validated spec the detector implements |

## Audit lessons that bind this project from day one

The continuation-program audit (docs/audits/2026-08-04-auditor-report.md)
lands here with force: the detector's inputs get a full channel-family
traversal (not adjacency from what anyone names); every threshold ships
measured-or-marked-conventional; labels derive from the decision (enter the
turnover cycle), clock-conditioned; and closure criteria assert artifact
properties — a detector "works" when the 7/22 and 7/31 replays and a
false-positive rate say so, not when its process ran.

## Sequencing

1. R2 + R3 research first (they gate everything phone-side and are
   independent of market hours).
2. R4 formalization + R1 detector spec (replay-driven; can run any evening).
3. Steve's architecture ruling off the R2/R3 decision memo.
4. Build phase gets planned then — detector → alert → staged execution, a
   paper pilot before anything touches a real order.

## Open decisions for Steve (not needed yet)

- Architecture A/B/C after the R3 memo.
- Whether alert-only ships as its own milestone ahead of phone execution
  (recommended: yes — value lands weeks earlier, risk is zero).
- Where ClaudeClaw should live and run if R2 recommends it.
