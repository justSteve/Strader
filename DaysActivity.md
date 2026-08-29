# DaysActivity - 2026-08-29

## 11:28 - Session Handoff [Recovery: Final-Hour Acuity Stages 2-3; Sunday-reopen feeder fix]

**Summary**: Recovered the mis-closed 06:36 session (nothing uncommitted, no handoff written) and resumed Final-Hour Acuity (st-g0jo): Stages 2-3 built, run and pushed — no lens carries a 14:00 direction call across 286 days; then fixed the Sunday-reopen feeder crash (st-wnuk) before it re-fires tomorrow 17:00 CT.

**Open Work**:
- st-g0jo Final-Hour Acuity — Stages 0-3 done. Next in order: (a) the hand read's combination (box position × energy × Mancini floor) as one pre-registered rule; (b) GEX lens from the state-tier strikes on the accruing days (the coded rule reads classic majors and disagreed with the 08-28 hand read); (c) st-9i7a / st-vl3c T-15 features; (d) Stage 4 page + drill on the 858 rows. OPRA stops 07-30 — an August pull is Steve's call.
- st-wnuk — code fix live at tonight's CT-midnight feeder restart (before Sunday 17:00). NEEDS STEVE, one line: `bash deploy/install.sh` to put the unit's restart backoff into /etc (no restart needed).
- Schwab token expires Mon 08-31 04:23 CT, before the open (st-40mp) — this is the one reminder.
- Desk page `desk-final-hour-lens-calls.html` was still in the plain-words gate (desk-translate, ~20 min on a glossary-heavy doc) at handoff; if absent next session, re-render: `bash /root/projects/COO/tmuxMOO/bin/desk-html.sh docs/measurement/final-hour-lens-calls-2026-08-29.md /var/moo/desk/desk-final-hour-lens-calls.html`.
- st-5wk8 (filed by tap-in): the liveness probe reports ES tape / MBP-1 STALE because it looks only for raw .jsonl; Friday's tape is on disk as .jsonl.gz.

**Tried**:
- Pre-registered lens rules at 14:00 → footprint pooled edge +0, Mancini +1; both flip sign 2025→2026; directional calls lose in premium (median −24% / −5%). Down rules failed a half at every T. Only survivor: footprint up at 14:45 (+20/+27, n=40, ~3-pt median), about half of which is the sample's own late-day up-lean.
- Notes on st-g0jo were overwritten with `bd update --notes` (should have been `--append-notes`); restored by hand with both Stage 1 and Stage 2-3 text.

**Files Changed**:
scripts/measurement/final_hour_lens.py
scripts/measurement/final_hour_lens_summary.py
docs/measurement/final-hour-lens-calls-2026-08-29.md
docs/plans/2026-08-28-final-hour-acuity.md
scripts/live_footprint_feed.py
tests/scripts/test_developing_bar.py
deploy/systemd/strader-footprint-feed.service
CurrentStatus.md

---
