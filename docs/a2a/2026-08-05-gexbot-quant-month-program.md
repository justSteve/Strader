# GexBot Quant Month — Program Brief (COO → Strader)

**Date:** 2026-08-05 · **From:** COO · **Beads:** st-ox9x (backfill), st-fyey (orderflow capture), st-trbn (retro cut), st-lstj (live gate), st-cgb (canonical-vs-measured), st-roj9 (distiller V2), st-p3lv (collection service)

## What changed today

- GexBot resumed after the Jul-03 pause: **State tier in the morning, upgraded to Quant ($350/mo) in the afternoon.** Steve is paying for **one month**, primarily for the 90-day `/hist` historical window. His words: *"This is a chunk $$ out of pocket — I'm counting on the two of you to leverage it into profit."* That is the program's success criterion.
- **Live collection is running**: gexbot-only poller (`scripts/corpus_poll_gexbot.py`), 60s cadence, tmux `steves-desk:gexbot-collect`, now a 6-endpoint cycle (4 state surfaces + classic majors + `/orderflow/orderflow` as an optional leg that skips silently when not entitled). First captured session: today's — including the 14:55 CT closing flush with net GEX volume spiking to −1.65M as price broke the put wall. One gap: 14:41–14:58 CT lost to a poller bug (fixed same hour).
- **The 90-day backfill is running now** (`scripts/gexbot_hist_backfill.py`, log at `/var/moo/logs/gexbot-hist-backfill-20260805.log`). Files land at `data/corpus/gexbot-hist/<date>/<package>_<category>.json.gz` with a `manifest.jsonl` recording fetched/denied/no-file per combo. These are full intraday per-strike time series — ~65–113 MB gzipped per category-day.

## Entitlement matrix (as observed with the live Quant key, day one)

| Combo | Status |
|---|---|
| hist `state` greeks (gamma/delta/charm/vanna, zero+one) | ✓ fetched (some 403s are *throttling in disguise* — the script retries with backoff before believing a denial) |
| hist `classic gex_full` | ✓ fetched |
| hist `state gex_*`, `classic gex_zero/one` | consistently 403 — apparent real gaps; manifest will confirm across the full run |
| `/orderflow` (live and hist) | ✓ **RESOLVED — entitlement is live; do NOT raise with the vendor.** Day one returned "User is not subscribed to Orderflow package", but that cleared by 2026-08-07: live capture pulled `/SPX/orderflow/orderflow` 1,135 times that day (one read-timeout, zero denials), and `orderflow_orderflow.json.gz` is present for every harvested hist day — the 63-day 1s archive behind every measurement round IS that data. Corrected 2026-08-10; the stale row had been carried forward three times. |

## The profit path, ranked (COO's read — the science is yours)

1. **Retro Gamma Cut (st-trbn) — the decision-maker.** Join backfilled gamma (sign, distance-to-flip, wall position at confirm time) to acuity run 2's 353 confirms. The recognizer is 47% unfiltered; day-shape hindsight cuts spread 65/47/32. If gamma regime — which IS knowable live — separates anywhere near that, the recognizer graduates from detector to filter and Steve trades only good-cohort confirms through the FD0/continuation lane. Un-defers the moment the backfill completes. Days, not months.
2. **Live Gamma Gate (st-lstj).** Wire `gex_sign` + journal gamma context per confirm. Forward evidence starts accruing immediately and never depends on the subscription tier staying at Quant.
3. **Distiller V2 (st-roj9) before trusting any distilled read.** V1 is discredited: replayed against its own captures it called a 190-pt slide "pinning" on 62% of RTH cycles, its confidence ordering inverted, and its zero-gamma transition check read a field the state endpoint never carries (it lives in classic majors — verified live today). The 06-09 crash capture is the regression fixture; the backfill supplies the 20+ calibration days its own docstring asked for and never got (~60 available).
4. **Canonical-vs-measured (st-cgb).** jass's two cross-confirmed rules (vol-direction × long-gamma continuation/fade; the two-signal fade entry) finally testable against ~60 days of ladders.
5. **Orderflow fields (st-fyey)** — collector leg deployed and waiting; blocked on the entitlement issue above.

## Ownership split

COO: collection infrastructure, backfill completion + manifest, supervised service (st-p3lv), subscription-state bookkeeping. **Strader: everything measured** — the retro cut, the gate design, distiller V2 calibration, doctrine tests. Domain rule stands: COO does not write Strader's strategy code.

## Month calendar

- **Aug 5**: harvest running; live capture running.
- **Backfill + a few days**: st-trbn first read.
- **~Aug 12**: checkpoint — does the gamma cut separate? Orderflow entitlement resolved?
- **~Sep 1-2 (before renewal)**: final hist sweep of the month's own dates, then Steve's downgrade decision (Quant → State keeps the live gate; all harvested history is permanent either way).
