# DaysActivity - 2026-06-24

## st-nd5 — Long single-option directional strategy (scoping PARKED mid-thread)

Steve redirected to another thread before completing. Resume here. (Intended target was a `bd update st-nd5 --append-notes`, but **bd writes are blocked** by a pending v51→v53 schema migration — see note at bottom. Corrected strategy understanding is also persisted in memory: `buying-movement-short-hold`, `singles-as-futures-proxy`, `carmine-rosato`.)

**Frame:** trade short-term 0DTE long singles as a **futures proxy** — "a single is a futures contract on its last day." Start from a working futures/scalp playbook; adjust ONLY where Greeks force it (theta cliff, gamma convexity, spread friction). Litmus = **delta, not theta**. Model = Carmine Rosato: order flow + supply/demand zones, primarily BOD, 8–15pt moves in <15min, targets/SLs = LuxAlgo confluence. Fly-vs-single comparison set aside per Steve (flies are a separate delta-first play: V-dump entry, 3/5-lot, scale off, leave a runner for pin).

**Favorable entry conditions (draft):**
1. Order-flow conviction (CumDelta / Footprint)
2. Confluence entry at a LuxAlgo zone with a target zone 8–15pts away
3. Negative GEX / room to the magnet (distance-to-magnet = directional fuel)
4. Range/pace expansion (realized travel at his cadence)
5. Breadth confirm ($TICK)

**Kills it:** chop between zones, positive-GEX compression, no order-flow read, mid-range with no clean zone in reach.

**Vol nuance:** it's PACE/realized movement over the hold, not IV level. EOD: vega≈0 → pure gamma/movement; IV only sets entry cost. AM = biggest/cleanest thrusts (Carmine BOD); EOD = cheapest entries + max gamma but steeper theta cliff.

**Open question to detail next:** which chart elements most directly support singles ENTRY and MANAGEMENT. Candidates: order flow (CumDelta divergence, Footprint absorption/exhaustion), LuxAlgo PAC order blocks / S-R zones (give both target AND stop), VWAP + bands, volume-profile nodes (HVN stall / LVN run), GEX sign + magnet distance, $TICK/$ADD breadth. Then define "A+ directional setup."

**[ALERT] Analytic gap:** the 06-09 study ("hot 2:30 → 69% of flies end dead") likely scored TERMINAL/close value, not the in-flight repricing actually captured. For singles, re-measure as directional continuation / max-favorable-excursion (MFE) WITHIN a short hold, hot vs calm afternoons. Ties to st-r2o.1 (convexity/V metric). Confirm 06-09 scoring method before scoping the re-run.

---

**[BLOCKED] bd writes gated by schema migration.** `bd update`/`bd close` refuse on this clone: pending v51→v53 migrations on a now-remote-backed DB (config drifted to a file remote via co-ssv8). Strader must NOT run `BD_ALLOW_REMOTE_MIGRATE=1 bd migrate` or `bd bootstrap` (COO is the designated migrator; bootstrap corrupts per beads-recovery doctrine). **Action needed from COO:** migrate once and `bd dolt push`, then this clone adopts it. Until then, beads is read-only here.
