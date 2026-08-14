---
type: playbook
title: "Selective Range Scalping"
description: "Strategy 3 (exploratory) — A+ PAC level bounces only, 2–3 per session, 3–5 SPX point targets sized to beat option spread friction"
timestamp: 2026-08-14T06:05:59-05:00
metadata:
  authorizing_bead: st-ylqw
  status: exploratory
  demoted_from: CLAUDE.md
---

Selective Range Scalping is **Strategy 3**, and it is **exploratory** — that is
the status it carried in CLAUDE.md and it was never promoted past it. Nothing
here is settled method; treat it as a candidate, not a playbook Steve runs.

It approximates an /ES scalper's approach using SPX options, at any time of
session, only at A+ levels.

## The play

**Setup.** LuxAlgo Price Action Concepts identifies clear support/resistance
boundaries with intraday range behavior. Session Volume Profile nodes
corroborate: a high-volume node is where price stalls, a low-volume node is
where it travels.

**Entry.** Only at A+ level bounces — **2–3 trades per session maximum**, not
every oscillation. Overtrading is the named failure mode of this strategy, and
the reason the cap is written into the setup rather than left to judgment.

**Target.** 3–5 SPX points. That is wider than a futures scalper's take,
deliberately: the spread must be overcome before the move counts.

**Friction rule.** SPX option bid/ask spreads ($0.10–0.30) are meaningful on
small moves. Prefer slightly ITM strikes, where the spread is tighter relative
to the expected move.

**Background filters.** GEX alignment — do not scalp into a wall. Cumulative
Delta at the level — absorption confirms the bounce.

**Why:** this was found as a **second documentation hole** during the [[st-ylqw]]
verification. [[pac-order-blocks-for-strike-centering]] covers PAC only for fly
strike centering, so demoting Strategy 3 out of CLAUDE.md would have landed it on
nothing — a deletion disguised as a move. The acceptance criterion for that
change was that every removed claim already lives in `knowledge/`; this file is
what made that true.

**How to apply:** hold the exploratory status when discussing it — do not
present it as established method or fold it into a session plan unprompted. The
overtrading cap and the friction rule are the two parts that bind. Steve's
[[scalper-mentality]] makes this the strategy most likely to be over-traded, so
the 2–3 cap is the part to defend. Related: [[orb-playbook]],
[[singles-as-futures-proxy]].
