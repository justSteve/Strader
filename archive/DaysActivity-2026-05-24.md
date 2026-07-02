# DaysActivity - 2026-05-24

## 08:40 - Session Handoff [V-detection v0 build]

**Summary**: Built end-to-end V-day detection pipeline for st-r2o — definition doc, streaming detector, eyeball-validation checklist generator, and TV-style local chart renderer. First-cut detector flagged 22 V-days (9.1%) across 243 corpus days; awaiting Steve's eyeball verdicts on a 35-row validation checklist before parameter tuning and the greek-correlation pass.

**Open Work**:
- st-r2o (in_progress, P1) — V-detector v0 built; awaiting Steve's eyeball-check on the 35-row validation checklist (`docs/measurement/v_day_eyeball_v0.md`) before parameter tuning + greek correlation pass. Charts pre-rendered to `data/measurement/charts/` with trough/peak markers and VWAP_p line overlaid.
- st-u29 (open, P3) — TV chart URL helper. Created this session as the deferred counterpart to the local-chart path; pick up if/when ad-hoc TV reviews start feeling slow.

**Tried**:
- ES morning backfill (st-r2o.1) to enable morning-VWAP-anchored detector → cost-probed at ~$50 (GLBX is metered separately from OPRA's flat fee, contrary to initial assumption); Steve declined → reframed v0 detector to use a 30-min pre-V baseline [13:00, 13:30) CT instead of morning VWAP. Known limitation called out in the def doc: v0 catches the post-13:00 V subset and likely false-negatives 20-40% of doctrine-V days where the consolidation broke before 13:00.
- Subagent-driven /checkpoint writes → blocked by write permission on `checkpoint.json` (confirms the `feedback_checkpoint_inline` memory). Switched to inline writes from main agent for the whole session.
- TradingView URL date navigation for chart eyeballing → confirmed via TV's own docs that the public chart URL supports `symbol`/`interval` only, no date param (UI-only). Pivoted to local `lightweight-charts` HTML rendering — TV-style candles via CDN script, no Python dep added.

**Files Changed**:
docs/measurement/v_day_definition.md
docs/measurement/v_day_eyeball_v0.md
scripts/measurement/detect_v_days.py
scripts/measurement/build_eyeball_checklist.py
tools/local_chart.py
data/measurement/v_days.jsonl
data/measurement/charts/ (35 rendered HTML charts)
scripts/corpus_backfill_databento.py (added --force flag for window-extending re-pulls)

---
