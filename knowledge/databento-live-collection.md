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

**Billing (corrected 2026-06-08 — I had this wrong):** Live OPRA streaming is **covered by Steve's flat Databento subscription** — "OPRA Equity Options, Standard, $199/mo, Live data: Active." Running the live collector incurs **no incremental per-GB charge**. The `metadata.list_unit_prices` endpoint returns **pay-as-you-go list rates** ($336/GB live OPRA trades etc.) that do NOT apply to subscribed live data — do NOT quote them as Steve's cost. The only *variable* DB billing is **historical** pulls (usage-rated), which we draw on only for specific backfill/gap-fill questions. Do NOT trust the repo's generic "live incurs metered cost" code comments (`market/ingest/databento.py:15`, `hello_databento.py:14`) over the subscription page — the subscription is authoritative.

**How to apply:**
- The live collector is `scripts/corpus_stream_databento.py` — one `LiveClient` per dataset on its own thread (OPRA.PILLAR + GLBX.MDP3 are separate gateways, can't share a session). Default window 13:00–15:00 CT.
- `--probe SECONDS` and `--max-ticks`/`--max-seconds` caps exist for **mechanical validation and scope control**, not cost gating (live is sub-covered). Still validate the live path before auto-scheduling.
- **Two-layer persistence:** (1) lossless raw-DBN archive teed via `LiveClient.tee_raw` → `databento_opra.{N}.dbn` (one segment per connection; every field incl. sequence/flags/ns ts/SymbolMappingMsg; replayable via `DBNStore.from_file`; this is the source of truth). (2) JSONL working copy `databento_opra.jsonl` (schema-matched to batch; ns ts preserved via pandas Timestamp; `action`="T", `sequence`/`flags` null — recover from DBN if needed). `--no-raw` disables layer 1.
- **T+1 compaction:** `scripts/corpus_compact_databento.py --yesterday` packs `.dbn`→`.dbn.zst` (zstandard, stays DBNStore-readable) and `.jsonl`→`.jsonl.gz`. JSONL is ~250-370 MB/day raw (~40% boilerplate); compaction is the lean-storage step. Wire to a T+1 weekday cron.
- **CRITICAL FIX (2026-06-08):** `LiveClient` symbol map was populated from `stype_in_symbol` (collapsed every contract to parent "SPXW.OPT") — fixed to `stype_out_symbol` (resolves per-contract OCC like "SPXW  260608C05500000"). Live probe caught it; regression test in `test_ingest_databento.py`.
- Batch puller (`corpus_pull_databento*.py`) stays for backfill/gap-fill (this IS usage-billed historical).
- **Entitlements (confirmed 2026-06-08):** OPRA live sub only; NO GLBX/ES live sub. Forward shape is a hybrid — OPRA collected **live** (sub-covered), ES collected **T+1 batch** (`corpus_pull_databento_es.py`, ~$0.09/day historical). The live collector defaults to `--streams opra` so it can't accidentally stream live GLBX at pay-as-you-go rates.

Related: [[project_schwab_auth_pattern]], [[feedback_v_day_target_is_down_only]].
