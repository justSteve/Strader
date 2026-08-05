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

## Amendment 2026-08-04 (same day) — ClaudeClaw vetoed; Claude-native path is primary

Steve vetoed ClaudeClaw/Telegram and redirected to the channel he already uses
daily: **Claude iOS via Remote Control**. The original candidate list missed
it — an instance-level enumeration of "push services" instead of a traversal
of "channels already open between Steve and this machine"; the audit's exact
class of failure, caught by the operator again. Verified against the harness
tool contracts (not assumed):

- **PushNotification** — a session's push "if Remote Control is connected,
  also pushes to their phone."
- **Monitor** — a session can persistently tail the detector's event journal
  (or a WebSocket) and react to each event.

**New primary architecture [D]** — the Strader desk session *is* the
intermediary: detector event → Monitor → PushNotification → Steve opens the
session from his phone → it presents the staged single ticket with the
evidence → he confirms in conversation → session fires via Schwab REST →
append-only journal. Rails unchanged; the confirm step gains the ability to
interrogate before firing; no new exposed surface and no third party in the
order path. [A] Tailscale PWA demoted to fallback; [B] Telegram dead.

R2's first question is now the notification's delivery semantics (app
backgrounded, Remote Control not attached, iOS Focus) — and a dumb-pipe
critical-alert backup fired straight from the daemon stays REQUIRED, because
the guaranteed ping must not depend on a Claude session being alive (the
2026-08-04 spend-limit event that killed a running agent is the live example
of that failure mode).

## Amendment 2, 2026-08-04 (same day) — Steve's counter-ruling: form fires, session thinks

Steve demoted [D]-as-trigger on two grounds: observed agent processing lag is
too slow for the fire moment, and a purpose-built web form beats a wall of
chat text as an execution canvas. Accepted, with one supporting fact from the
RC doc: while Remote Control is connected, the session transcript is stored
on Anthropic servers — the Tailscale form keeps order details phone→local.

**Final shape:**
- **Fire surface: [A] Tailscale-private web form** — staged single ticket,
  FIRE + confirm, hard caps, kill switch, append-only journal.
- **Alert: dumb-pipe critical push carrying the form URL** (tap → form, no
  chat hop), with Claude-native push as the redundant second ping.
- **Claude session: staging brain, watchdog, and optional depth** — open it
  from the phone when you want to interrogate the setup; never required to
  fire.

Two findings from the official RC doc land regardless of architecture:
- **Hard-wire exists**: `/config` → *Enable Remote Control for all sessions*
  = `true`. One toggle, user-level, covers every COO and Strader session on
  this box; sessions appear by name under Code in the app. Push toggles:
  *Push when Claude decides* / *Push when actions required*.
- **"Not in my chair" gating exists natively**: pushes are skipped while
  focused on the terminal, and `CLAUDE_CLIENT_PRESENCE_FILE` (v2.1.181+)
  extends suppression to any-time-at-the-machine via a screen-lock-driven
  marker file — the exact away-detection this project needs, and a pattern
  the dumb-pipe leg should copy.

## Status 2026-08-05 — two of four lanes closed, both halves of the remote arm exist

| Piece | State |
|---|---|
| Transport | **DONE** — Tailscale node `mydesk-1` (100.108.58.5); HTTPS via `tailscale serve`, tailnet-only, funnel prohibited |
| Fire surface | **DONE (dry-run)** — `scripts/fire_server.py` at https://mydesk-1.tail89f676.ts.net; staged-ticket form, ARM→nonce→FIRE, exit-all panic button, all rails, nothing transmittable |
| Alert leg | **DONE, verified live** — `strader/alerts.py` → Pushover; raw Python to phone, no Claude session in the path (st-mk56) |
| Order client | **BLOCKED on Steve** — `~/.schwab_fire_key`, then preview-only milestone (st-bxls) |
| Detector | **OPEN** — R1/R4: what fires the alert, and how the "obvious line" is measured |

The remaining risk moved entirely into the detector. Everything downstream of
"a flush is happening" now works and has been exercised by hand.

## Open decisions for Steve (not needed yet)
- Whether alert-only ships as its own milestone ahead of phone execution
  (recommended: yes — value lands weeks earlier, risk is zero).
