---
type: playbook
title: "ORB Playbook"
description: "Strategy 2 — the mechanical 8:30–10:00 CT opening range breakout on LuxAlgo Ultimate ORB: HV signals only, ATR trail, take Target 1, one trade per morning"
timestamp: 2026-08-14T06:05:59-05:00
metadata:
  authorizing_bead: st-ylqw
  status_ruling: "Steve, 2026-08-13 — 'orb not dead'"
  demoted_from: CLAUDE.md
---

Opening Range Breakouts are **Strategy 2** — the mechanical morning play,
operating **8:30–10:00 CT**. It complements the late-day flies by living at the
opposite end of the session, so the two never compete for attention.

Steve ruled on 2026-08-13 that **ORB is not dead**. It came out of CLAUDE.md in
the [[st-ylqw]] scope change because its mechanics are not action-bearing as
always-loaded context, not because the play was retired. This concept is the
home those mechanics moved to.

## The play

**Tool.** LuxAlgo Ultimate ORB is the primary instrument. It defines the
opening range high/low automatically for the configured session window and
provides volume-qualified breakout signals (HV/LV), an ATR trailing stop with a
built-in stop optimizer, extension targets, and a hit-rate dashboard.

**Entry.** HV (high-volume) breakout signals **only**. LV breakouts get a tight
leash or are skipped entirely. The volume qualification *is* the false-breakout
filter, and it is why this play requires no numbers work from Steve.

**Stop.** ATR-based trailing stop. Use the indicator's stop optimizer to select
the multiplier rather than hand-tuning it.

**Target.** Take Target 1 and walk away. Cross-check against GEX first: a GEX
wall sitting between price and the target means the target probably does not get
hit — skip the trade or downgrade the expectation.

**Cadence.** One trade per morning. The edge is mechanical rules plus volume
qualification, not read-the-tape discretion — which is exactly what makes it
suitable while price-action literacy is still being built ([[st-ylqw]] mission).

## Context frame

Market Profile **Initial Balance** (first 30–60 min) frames the ORB context;
VWAP is the sanity benchmark.

Background filters Strader watches and surfaces only when load-bearing:

- **$TICK** — breakout plus a $TICK extreme is conviction.
- **Cumulative Delta** — confirms breakout conviction; divergence warns.
- **GEX sign** — positive (mean-revert regime) is hostile to continuation;
  negative (trending regime) favors it.

**Why:** this is Steve's only mechanical, rules-first play. Everything else in
the book asks him to read something. Keeping it intact and unelaborated is the
point — see [[scalper-mentality]] for why the 15-minute-style rules stay
deliberately un-formalized elsewhere.

**How to apply:** when Steve is in the 8:30–10:00 window, this is the play on
the table. Check the GEX wall before endorsing Target 1. Do not add discretion
to it, and do not reconstruct these rules from memory — read them here.
Related: [[selective-range-scalping]], [[directional-gex-butterflies]].
