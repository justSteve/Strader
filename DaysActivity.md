# DaysActivity - 2026-08-09

## 21:55 - Session Handoff [GexBot gate + supervision, EOD ritual]

**Summary**: Closed the GexBot collector's two opposite failures — it ran 24/7 with no session gate and had no supervisor to restart it — then built the EOD ritual, which closes a trading day rather than a session, so a day like 2026-08-08 cannot again end with its only record inside a commit message.

**Open Work**:
- `st-p3lv` (in_progress) — GexBot supervisor installed and smoke-tested, but it has never run a real session. First unattended fire is Monday 2026-08-10 07:30 CT. Close it once one full session collects >300 cycles with no hand-holding.
- `st-z92a` (in_progress) — EOD ritual built and cron-installed; the ritual has not run once. First packet fires Monday 15:15 CT; close when one cycle has produced a Day Close entry that `--audit` accepts.
- `st-x2mp` (in_progress) — live/replay parity tool committed (`c8138dc`) and green, but exercised replay-to-replay only. The live-vs-replay measurement it exists for needs a live feeder; Monday is the first opportunity.
- `st-k68o` (in_progress, P1) — counter-dictum program charter, plus two new studies in the ready queue (`st-1bv1` clock-family traversal, `st-56pu` pre-green stop budget). This is the current focus and this session did not touch it.
- `st-a6zm` closed. Duplicates closed: `st-fo6j` (dup of `st-v5a8`, midday no-trade window), `st-5uqz` (dup of `st-av7b`, Pine sticky `rcl`) — both filed on a tap-in claim that those items were un-beaded. They were beaded on 08-07. Check `bd list` before filing off a briefing.

**Tried**:
- Reading the tap-in briefing's "not yet beaded" items as fact → **wrong**, twice. Both were already beaded on 08-07 with better descriptions than the ones I wrote. A briefing's claim about what does not exist is the claim most worth checking.
- A systemd user unit for the GexBot collector, which `st-p3lv` explicitly argued for → **rejected on a corrected premise**. The bead's reasoning was that the 2026-08-05 19:55 tmux death took the capture supervisor down with its collectors, so a tmux-hosted supervisor cannot be trusted. But that supervisor is a *cron* job, and its wrapper has a `has-session` branch that bootstraps a session when the socket is gone. What actually happened at 19:55 is that it is outside the 02:50–15:05 capture window, so the supervisor correctly stood down; GexBot, having no supervisor at all, stayed dead. Reused the existing cron supervisor as a second tenant instead — six env knobs, no second copy of its process-identity and restart-safety reasoning. Erratum recorded in `CurrentStatus.md`.
- Pointing the ES supervisor's `globex_open` at the new NYSE holiday table, since it admits holidays are unmodeled → **rejected**. CME equity-index futures trade shortened sessions on most NYSE closures, so an NYSE-closed day is a day ES really is printing; calling it closed would suppress a genuine `stale` verdict seven times a year. Added a `--venue` switch instead: `cash` is holiday-aware, `globex` stays deliberately blind.
- Restructuring `DaysActivity.md` to be day-keyed with sessions as spans inside it → **rejected**. The file exists in 9+ enterprise repos and its format is COO's authority. A trading day is the one thing only Strader has, which justifies a Strader-only sibling ritual, not a convention change. `/handoff`, `/tap-in`'s roll and the archive step are untouched.
- Having a cron-fired agent write the Day Close entry unattended → **rejected** in favour of the split Steve already ruled for `/mancini-parse` (`st-lw58`): cron prepares and alerts, the skill interprets. Cron writes facts to `data/eod/<date>.md`; an agent writes the reading. The packet is durable on disk *before* any agent reads it, because the failure being fixed is a day whose facts evaporated with nobody at the desk — a packet living only inside a session that may never happen reproduces the bug.
- Alerting on every gap the packet finds → **rejected**. Only hard gaps alert (a stream at 0 cycles, or GEX rows outside the collect window). An ungraded call is for `/eod` to notice; an alert that fires most days is not an alert.

**Files Changed**:
strader/market_calendar.py
strader/capture_health.py
strader/tests/test_market_calendar.py
strader/tests/test_capture_health.py
scripts/corpus_poll_gexbot.py
scripts/capture_health.py
scripts/eod_packet.py
scripts/surface_liveness.sh
scripts/cron/capture-supervisor-wrapper.sh
scripts/cron/gexbot-supervisor-session.sh
scripts/cron/eod-packet-wrapper.sh
scripts/live_footprint_feed.py
scripts/live_parity_check.py
scripts/cron/live-parity-wrapper.sh
market/orderflow/run_log.py
market/orderflow/parity.py
tests/scripts/test_eod_packet.py
tests/scripts/test_capture_supervisor_wrapper.py
tests/market/orderflow/test_run_log.py
.claude/skills/eod/SKILL.md
.claude/skills/handoff/SKILL.md
.claude/skills/tap-in/SKILL.md
.claude/skills/daysactivity-format/SKILL.md
CurrentStatus.md
pyproject.toml

---
