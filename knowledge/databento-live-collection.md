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

**Billing (figures moved out of this doc 2026-08-13, st-g0or):**
Which plan we hold, what it costs, what was cancelled and when — all of it lives in
**one** place now, `config/entitlements.yaml`, and is read by running the probe rather
than by remembering:

```bash
.venv/bin/python3 scripts/entitlements_probe.py
```

Do not restate plan names, tiers, prices, or cancellation dates here. Twice this doc
carried them and twice they went stale silently — it asserted a cancelled OPRA sub as
"Live data: Active" for a week after the swap (st-onr4), which is the incident that
produced the registry.

The billing *shape*, which survives whatever plan is current:

- Live streaming is **sub-covered** — `--probe SECONDS` and `--max-ticks`/`--max-seconds`
  exist for mechanical validation and scope control, **not** cost gating.
- Historical pulls are a different animal: a dataset we hold **live** is flat-rate, and a
  dataset we do **not** hold is **usage-billed per pull**. Check the registry before
  backfilling, and treat a pull of a non-subscribed dataset as a spend decision rather
  than a technical one.
- `metadata.list_unit_prices` returns pay-as-you-go **list** rates that do NOT apply to
  subscribed live data — never quote them as Steve's cost.
- Subscription facts are **probed at statement time, never recalled from this doc**. This
  doc records the decision shape only.

**How to apply:**
- The live collector is `scripts/corpus_stream_databento.py` — one `LiveClient` per dataset on its own thread (OPRA.PILLAR + GLBX.MDP3 are separate gateways, can't share a session). Default window 13:00–15:00 CT.
- **Capture window = the Globex day since 2026-08-18 (st-9olq).** Three systemd timers, one process each, all writing the calendar day's directory: `strader-capture-early` 00:00→02:50 CT Mon–Fri, `strader-capture` 02:50→15:05 (Steve's st-btu ruling, unchanged), `strader-capture-evening` 15:06→23:59:59 Mon–Thu, Fri 16:05 (CME close), Sun 17:00 reopen. Before that date the corpus holds 02:50–15:05 only, so the ~11 h nightly hole is a property of days ≤ 2026-08-17, not of the feed. Steve's conditions for the extension, both measured that day: cost is sub-covered on the CME/Futures plan (no per-hour or per-GB charge on live GLBX), and disk was 783 GB free of 1007 GB with the T+1 compaction packing a day from ~2.3 GB raw to ~200 MB. Units live in `deploy/systemd/`; the assessor (`scripts/health_assessors.sh`) watches the whole day against the Globex calendar.
- `--probe SECONDS` and `--max-ticks`/`--max-seconds` caps exist for **mechanical validation and scope control**, not cost gating (live is sub-covered). Still validate the live path before auto-scheduling.
- **Two-layer persistence:** (1) lossless raw-DBN archive teed via `LiveClient.tee_raw` → `databento_opra.{N}.dbn` (one segment per connection; every field incl. sequence/flags/ns ts/SymbolMappingMsg; replayable via `DBNStore.from_file`; this is the source of truth). (2) JSONL working copy `databento_opra.jsonl` (schema-matched to batch; ns ts preserved via pandas Timestamp; `action`="T", `sequence`/`flags` null — recover from DBN if needed). `--no-raw` disables layer 1.
- **T+1 compaction:** `scripts/corpus_compact_databento.py --yesterday` packs `.dbn`→`.dbn.zst` (zstandard, stays DBNStore-readable) and `.jsonl`→`.jsonl.gz`. JSONL is ~250-370 MB/day raw (~40% boilerplate); compaction is the lean-storage step. Wire to a T+1 weekday cron.
- **CRITICAL FIX (2026-06-08):** `LiveClient` symbol map was populated from `stype_in_symbol` (collapsed every contract to parent "SPXW.OPT") — fixed to `stype_out_symbol` (resolves per-contract OCC like "SPXW  260608C05500000"). Live probe caught it; regression test in `test_ingest_databento.py`.
- Batch puller (`corpus_pull_databento*.py`) stays for backfill/gap-fill (this IS usage-billed historical).
- **Entitlements — read them, don't recall them (st-g0or):** what we hold is in
  `config/entitlements.yaml`; run `.venv/bin/python3 scripts/entitlements_probe.py`
  before saying a word about which datasets are subscribed. The *collector's* shape
  follows from that file and is stated here because it is code, not billing: the default
  is `--streams es,es-mbp1` since st-13pi (`f9515de`, "default to the streams we actually
  hold, not cancelled OPRA"), the daily OPRA import was halted 2026-08-07 and removed from
  the datastream gate's required streams, and OPRA is fetched ad hoc when a specific
  question warrants the spend. If the registry ever says we hold a dataset the collector
  is not pulling, that mismatch is the finding.

Related: [[entitlements-registry]], [[project_schwab_auth_pattern]], [[feedback_v_day_target_is_down_only]].
