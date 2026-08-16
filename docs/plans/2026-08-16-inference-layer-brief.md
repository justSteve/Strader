---
title: Inference Layer Brief — Watcher V2 and the tiered read
date: 2026-08-16
author: Strader (st-slj4), with COO (co-mq9o5)
status: brief-for-Steve
---

# Inference Layer Brief — Watcher V2 and the tiered read

## The ask, and the answer

The Watcher V2 plan (`docs/plans/2026-08-16-watcher-v2-plan.md`) is presentation (cell cues, volume
profile), supervision (systemd units, health dots) and schema; on inference it says nothing — fair, you
didn't ask it to. But two pieces of it *are* the inference seam and should be shaped now:
Phase 3's versioned emission schema (`emission.v1.json`) plus `targets_for()` computed in
`StackDriver.on_bar` — that dict is the atom a model reads — and the bridge's replaced-not-appended slot
pattern (meta / final / developing / profile), because a "packet" is the same kind of view. An older bead,
**X-ray Harness** (`st-vqa`) — deterministic watcher ~90% of the time, agent switched on at pivotal moments
with a warm packet — already names the architecture; V2 doesn't reference it. Strader and COO agree on the
shape below and have filed the work.

## Where the cost and latency actually go today

Today a full Fable interactive session tails the sentinel alerts file (harness Monitor) and does the x-ray
read on each wake. Each wake carries the whole session context — 100k+ tokens — and the model then has to
go *find* the facts: read files, parse jsonl, 5–15 s per tool round-trip. Cost problem and latency problem,
one fix: code assembles the facts and hands them over in the first turn, so the model runs zero tools
before it reads.

## Three tiers, not two

| Tier | Who | What it does |
|---|---|---|
| 0 | Code | Recognizers (`ImbalanceStack`, `SweepPrint`, `DeltaDivergence`, `SetupRecognition`), sentinel level-proximity, anchored volume profile, level distances, basis |
| 1 | Cheap model — Claude Haiku 4.5, or Claude Sonnet 5 at low effort (1–3 s, structured JSON) | Narrator and triage: from a compact packet, emit a fixed-schema read |
| 2 | Claude Opus 5 / Fable, pivotal moments only | The x-ray read, coaching, "the tape contradicts the plan", direction-inversion calls |

Tier 0 is the codified playbook and it stays code — not a small model. Tier 1's schema is
`{lean: continuation | pivot | none, level_in_play, stage, confidence, escalate: true/false, one_line}`.

Your premise holds with one sharpening: a lower-tier model can handle *narration and triage against* a
codified playbook; the playbook checks themselves are code, and judgment and teaching stay with the big
model. Stated plainly, because it is a boundary and not a preference: **no model of any tier sits in an
execution path — code and Steve only.** Tier 1 narrates; tier 2 coaches. The development phase is where the
big model designs the packet schema and prompts and *grades* tier 1 against hindsight — where the
complexity you named actually lives.

## The packet

Push, not pull. From the 08-13 live run log: 932 bars, 264 recognizer emissions (152 SetupRecognition, 60
DeltaDivergence, 50 SweepPrint, 2 ImbalanceStack); sentinel alerts run 26–41/day. A bar identity record is
~60 tokens, an emission ~120.

A packet is: the last ~40 bars as OHLC+delta tape; emissions in that window with their `targets`; levels
with distance and domain; profile POC/VAH/VAL; recent sentinel alerts joined by `ts_row` (the tape second
the alert is *about*, not `ts_alert_utc`); context — GEX regime sign, session delta, day-type developing.
Roughly 3–4k tokens.

Domain is load-bearing: sentinel and GexBot are SPX with no live basis to ES yet, so every fact carries a
`domain` (or the Phase 3 basis field) or the small model subtracts apples from oranges.

Never send cells — the model reads a footprint worse than `find_imbalances` does. Send derived facts. The
stable system prompt (doctrine vocabulary plus schema) is cached for an hour and the packet is the volatile
suffix; cache minimums are 512 tokens on Opus 5, 1024 on Sonnet 5, 4096 on Haiku 4.5. When nothing emitted
and no level is in play the packet carries `quiet: true`, and the reader makes no call at all.

## Structure — COO's answers

Credited COO, 2026-08-16 (`co-mq9o5`):

- The packet builder is a pure function — `market/signals/packet.py: packet_for(state, bar_i)`, schema
  `market/signals/schema/packet.v1.json` — built from the *same* emission dicts `StackDriver.on_bar`
  produces after `targets_for()`; a second serialisation path would stop the parity snapshot meaning
  anything.
- Computed by the feeder on the closed-bar batch only, never the 1-second developing tick: a packet is a
  read-time view, not a heartbeat. Posted as a `packet` slot on the bridge, served on `/bars` and
  `GET /packet`, and reproducible offline from a run log byte-identical to live — test next to
  `test_parity_harness`, so hindsight grading grades what the live caller sees.
- Tier-1 caller: `scripts/tape_reader.py` under `strader-tape-reader.service` — `PartOf` the bridge unit,
  `After` the feeder, `Restart=on-failure`, its own `_tape_reader_health.json` for a health dot. Reads land
  as a `reads` slot (one caption line under the HUD, not a panel) *and* as append-only
  `data/corpus/<day>/orderflow_reads.jsonl`, the measurement record.
- Config is a small dataclass from env/CLI (model id, effort, cadence, wake rules, dry-run); the API key
  lives in an env file, never a unit file. Any API failure degrades to "reader off" — the chart never waits
  on it.
- Wake rules are code, unconditionally. The tier-2 wake is a pure predicate over packet + sentinel + tier-1
  output (SetupRecognition with `fire_index` ≤ 2, sentinel `approach`, tier-1 `escalate=true`, an N-bar
  cadence fallback) with a fixture test, so a replay can count a day's wakes before they cost anything.
  Tier 1 may *recommend* escalation; only code decides — same reason the sentinel has no LLM: proximity is
  arithmetic.
- COO's pushback, adopted: no fixed once-a-minute clock for tier 1. Wake it on the closed-bar batch (~1–2/min
  in RTH anyway) and skip on quiet — the quiet verdict is itself a measured stream.

## Cost and latency envelope

List prices verified 2026-08-16.

| Model | In / out per M tokens | Tier-1 upper bound: 390 calls × 4k in / 200 out |
|---|---|---|
| Fable | $10 / $50 | — (tier 2 only) |
| Opus 5 | $5 / $25 | — (tier 2 only) |
| Sonnet 5 | $3 / $15 (intro $2 / $10 through 2026-08-31) | ≈ $5/day |
| Haiku 4.5 | $1 / $5 | ≈ $2/day |

Those are before caching and the quiet-skip; realistic spend is well under half. Tier 2 at ~10 wakes/day ×
8k in / 800 out is ≈ $0.06 a call on Opus 5, ≈ $0.12 on Fable — under $1.50/day. One Fable interactive
session watching all day costs an order of magnitude more, and is slower: each read is a tool-fetching turn
measured in minutes.

Latency to first fact: bar close + one bridge poll (1–2 s) + packet build (ms) + a Haiku/Sonnet call
(1–3 s) — a read on screen under ~5 s after the bar closes, no tool round-trips.

Development spend: replay the 08-12/13/14 run logs into packets, through the Batches API at 50% off,
grading tier-1 reads against hindsight (the acuity sweep). Pre-Phase-0 run logs have no `end` record, so
the harness must not assume a final block.

## What's filed, and what needs you

Filed today: **Emission And Packet Schema** (`st-n0qm.5`), child of the Watcher V2 Epic (`st-n0qm`), owned
by Strader. One PR: `emission.v1` + `targets_for()` + `packet.v1` + one parity-snapshot regen + one
contract test; COO takes the bridge slot, unit and health dot. Two follow-on beads are filed behind it:
**Tier One Tape Reader** (`st-n0qm.6`) and **Hindsight Read Grading** (`st-n0qm.7`). Nothing displaces
Phase 2 / 2b — Phase 2 lands today; 0, 1 and 2b shipped this morning.

Three things need you:

1. **Spend.** OK to spend on a tier-1 model during development, at roughly the envelope above — and which
   one to start with. Strader's recommendation: Sonnet 5 at low effort while the intro price holds,
   dropping to Haiku once the grading says the packet is doing the work.
2. **The boundary, as written.** Confirm: no model in an execution path, ever.
3. **Where the read shows up.** The caption line on the footprint page, or the sentinel tmux window
   instead. Taste call.

---

Brief authored by Strader (st-slj4); structural answers by COO (co-mq9o5). Fable weekly budget is at 93%,
so drafting was delegated to Opus and edited by Strader.
