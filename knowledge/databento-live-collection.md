---
type: decision
title: "Databento Live Collection"
description: "Databento forward-collection mode is LIVE tick stream (chosen over T+1 batch), via scripts/corpus_stream_databento.py"
timestamp: 2026-06-08T12:22:12-05:00
metadata:
  originSessionId: b2027c43-26bd-45dc-a042-42bd001c8e71
  graduated_from: project_databento_live_collection.md
  source_type: project
---

Forward Databento collection runs as a **live tick stream**, not a daily T+1 batch. Steve chose live over batch on 2026-06-08 after being shown both options.

**Why:** Steve wants the datastreams (GexBot, Schwab, Databento) collected live; Databento's live feed is the chosen mechanism going forward. The 250 backfilled days remain T+1 batch — both sources write the same per-day corpus files (`databento_opra.jsonl`, `databento_glbx_es.jsonl`), distinguished by `provenance.source` ("live" vs absent/batch).

**Billing (rewritten 2026-08-12, st-onr4 — the 2026-06-08 state below no longer holds):**
The OPRA Equity Options plan ($199/mo) was **cancelled ~2026-08-04 and replaced by a
CME/Futures (GLBX) plan** (st-7av4; Steve confirmed from the billing portal). Live GLBX/ES
streaming is covered by that subscription; there is **no live OPRA entitlement anymore**.
Historical OPRA is pulled **ad hoc, usage-billed**, only when something specific warrants
it. As before: `metadata.list_unit_prices` returns pay-as-you-go list rates that do NOT
apply to subscribed live data — never quote them as Steve's cost. Subscription facts are
**probed at statement time, never recalled from this doc** — the billing portal and
CurrentStatus's data-surface table are the live source; this doc records the decision
shape only.

> **Superseded record (2026-06-08, kept for history):** "OPRA Equity Options, Standard,
> $199/mo, Live data: Active" — flat-sub OPRA live streaming, no incremental per-GB
> charge. True then, false since ~2026-08-04.

**How to apply:**
- The live collector is `scripts/corpus_stream_databento.py` — one `LiveClient` per dataset on its own thread (OPRA.PILLAR + GLBX.MDP3 are separate gateways, can't share a session). Default window 13:00–15:00 CT.
- `--probe SECONDS` and `--max-ticks`/`--max-seconds` caps exist for **mechanical validation and scope control**, not cost gating (live is sub-covered). Still validate the live path before auto-scheduling.
- **Two-layer persistence:** (1) lossless raw-DBN archive teed via `LiveClient.tee_raw` → `databento_opra.{N}.dbn` (one segment per connection; every field incl. sequence/flags/ns ts/SymbolMappingMsg; replayable via `DBNStore.from_file`; this is the source of truth). (2) JSONL working copy `databento_opra.jsonl` (schema-matched to batch; ns ts preserved via pandas Timestamp; `action`="T", `sequence`/`flags` null — recover from DBN if needed). `--no-raw` disables layer 1.
- **T+1 compaction:** `scripts/corpus_compact_databento.py --yesterday` packs `.dbn`→`.dbn.zst` (zstandard, stays DBNStore-readable) and `.jsonl`→`.jsonl.gz`. JSONL is ~250-370 MB/day raw (~40% boilerplate); compaction is the lean-storage step. Wire to a T+1 weekday cron.
- **CRITICAL FIX (2026-06-08):** `LiveClient` symbol map was populated from `stype_in_symbol` (collapsed every contract to parent "SPXW.OPT") — fixed to `stype_out_symbol` (resolves per-contract OCC like "SPXW  260608C05500000"). Live probe caught it; regression test in `test_ingest_databento.py`.
- Batch puller (`corpus_pull_databento*.py`) stays for backfill/gap-fill (this IS usage-billed historical).
- **Entitlements (rewritten 2026-08-12, st-onr4 — inverts the 2026-06-08 record):** GLBX/ES
  live sub only; NO OPRA live sub (cancelled ~2026-08-04, st-7av4). Forward shape: ES
  collected **live** (sub-covered) via `--streams es,es-mbp1` — the collector default
  since st-13pi (`f9515de`, "default to the streams we actually hold, not cancelled
  OPRA"). OPRA is **ad hoc historical only** (usage-billed), pulled when a specific
  question warrants it; the daily OPRA import was halted 2026-08-07 and removed from the
  datastream gate's required streams.

Related: [[project_schwab_auth_pattern]], [[feedback_v_day_target_is_down_only]].
