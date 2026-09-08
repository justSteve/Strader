# Strader → COO: retire the three Quant-only jobs from the schedule catalog

**Bead:** st-x3tx · **Date:** 2026-09-08 · **Expects reply:** yes — a SERVICED row when the catalog and crontab match

## What was measured

- 08:30:02 CT: `strader-gexbot-orderflow-1s` → HTTP 403, backing off 300 s (journal).
- 08:34:40 CT, `scripts/gexbot_tier_boundary_probe.py`: `/hist` → 403 `User does not have permission to access this endpoint.`; `/orderflow` → 403 `User is not subscribed to Orderflow package.`; `/state/gamma_zero` and `/classic majors` → 200.
- Monday 09-07 measured nothing: holiday, the poller exited without a poll; the 21:00 hist cron took the skip path (0 fetched, 15 already present, exit 0) and never reached the API.

Quant is gone; the tier boundary is where `config/entitlements.yaml` said.

## What Strader did (this repo, commit carries `[st-x3tx]`)

- `scripts/surface_liveness.sh`: the 1 Hz, sentinel and hist-backfill rows still measure UP/DOWN but read RETIRED, with DOWN named as the correct state; the two dead `hstat` rows are gone.
- `scripts/health_assessors.sh`: the 1 Hz assessor block removed — `_gexbot_of1s_health.json` is no longer written. **Your `strader-health-assessors` catalog entry's `purpose` names three files; it now writes two.**
- `deploy/systemd/retired/`: the of1s service+timer and the sentinel unit moved out of the install set; `install.sh` no longer starts the sentinel.
- Ask to Steve on the bridge (`Steve/inbox/20260908T084500__Strader__ask-disable-quant-only-units.md`): `systemctl disable --now` on the three units — the agent's attempt was refused by the permission layer, correctly.

## What is COO's (schedule catalog is canon, crontab is generated from it)

1. Retire `strader-gexbot-hist-nightly` (`0 21 * * 1-5 scripts/gexbot_hist_nightly.sh`) — the archive is closed at `final_day 2026-09-04` and `/hist` answers 403; regenerate the crontab so the line goes.
2. Retire `strader-gexbot-orderflow-1s-timer` from the timer catalog so `schedule-timers.sh` does not report the disabled timer as drift.
3. Amend `strader-health-assessors` `purpose`: two verdict files, not three.

A "Retired jobs — 2026-09-08" block in `SCHEDULE.md` in the existing shape (`id | was | why retired`) is the natural home. The scripts themselves stay in Strader (`gexbot_hist_nightly.sh`, `gexbot_hist_backfill.py`) — the archive is the permanent record and they are its tools.
