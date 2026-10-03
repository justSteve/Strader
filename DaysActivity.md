# DaysActivity - 2026-10-02

## 21:03 - Session Handoff [execd: stop-after-fill, fast SEND, TOS journal, CLOSE, FLATTEN SPX]

**Summary**: Parsed Mancini for Fri 10-02 (60 levels, 7 commentary). Diagnosed the 11:02 7730C stop-out from the journal, the ES tape and Schwab's Message Center: the triggered bracket's STP 7.50 MARK child filled when the entry activated it, with the mark at 8.15. The entry now goes out alone and the stop goes on after the fill. Profiled and cut the click-to-SEND path from 8 broker calls to about 2–3. Removed the below-bid price floor. TOS orders are now journaled and shown as closed cards. The traffic pane shows newest first and every stop rest, move (with its cause) and fill. Added a per-position CLOSE. FLATTEN became FLATTEN SPX. execd runs 87dc301; 3b585b2 is pushed but not installed.

**Open Work**:
- st-lax0 (P1, next): FLATTEN SPX must close every SPX position the way it opened — spreads closed as one reversed multi-leg order, shorts bought to close. Steve 21:00 CT: "an endpoint rendered via our form's open positions card shall close all open spx positions without regard to how they opened." The spec is on the bead. It replaces the st-ld7i shorts guard. Needs BUY_TO_CLOSE and a multi-leg Schwab body, and Schwab's acceptance of multi-leg pricing measured first.
- st-jdk7 Spurious Mark Stop: built (a0165a7) and installed. Live trades on the new install show the stop resting after the fill (12:56, 13:08, 13:26 CT). Close once Steve agrees. Cause on Schwab's side unverified; Steve may post the request body to the schwab-py Discord.
- 3b585b2 FLATTEN SPX is pushed but not installed; Steve runs `bash deploy/install.sh --execd`.
- Two false outside_order lines (the 10:34 rejected bracket's legs, 1008154065058/059) stay in today's journal; the root_id fix stops recurrences.
- Schwab refresh token walls 2026-10-05 ~06:49 CT (Monday before the open); re-auth over the weekend.

**Files Changed**:
execd/bounds.py
execd/broker.py
execd/orderpage.py
execd/page.py
execd/panel.py
execd/paper.py
execd/schwab.py
execd/service.py
execd/traffic.py
execd/README.md
tests/execd/test_bounds.py
tests/execd/test_bracket.py
tests/execd/test_mode_switch.py
tests/execd/test_orderform.py
tests/execd/test_page.py
tests/execd/test_panel.py
tests/execd/test_reconcile.py
tests/execd/test_schwab.py
tests/execd/test_service.py
tests/execd/test_traffic.py
tests/execd/test_triggered.py
tests/execd/scenario/harness.py
tests/execd/scenario/test_audit_defects.py
tests/execd/scenario/test_page_flow.py
tests/execd/scenario/test_rearm.py
tests/execd/scenario/test_seed_0930.py
tests/execd/scenario/test_sequences.py
runbook/mancini/commentary/2026-10-02.jsonl
CurrentStatus.md

---

## 06:59 - Session Handoff [held push released, Mancini 10-01, execd rulings + order-form rebuild, bridge watch]

**Summary**: Released the push held behind st-5n3s (56 commits). Ran the Mancini parse for Thu 10-01 (57 levels, 7 commentary). Built Steve's two 10-01 execd rulings: dollar-only entry stop, and a refusal for a stop at or above the bid. Built the Desk view log, the order-form rebuild (strike sort, SEND traffic pane, strike pin, paper/live separation), and entry pricing at min(mid+0.05, ask) with a 0.30/contract default stop and re-arm after a stop-out. After reading today's two seconds-long stop-outs in the journal, added stop struck from the mid at fill, the broker preview dropped from SEND, and room-from-mark on the ticket. Everything is pushed. The last install Steve ran was 1e55681 (unlock 13:56 CT). dc39327 and 687b2c9 are NOT installed.

**Open Work**:
- Install: `bash deploy/install.sh --execd` while flat. It picks up dc39327 and 687b2c9: pricing, 0.30 stop, re-arm, stop-from-mark, no preview, room cue. Steve's /etc/execd/bounds.yaml still carries `preview_cost_tolerance_usd`; it is now a retired key and is ignored.
- Asked Steve, no answer yet (Deferred): should the Alpaca paper path also strike its stop from the mark? It still uses the fill price.
- Asked Steve, no answer yet (Deferred): restart the bridge watch? It hit the 2h background cap and the harness said not to re-arm. The `--until-event` + run_in_background design (st-4cmi) therefore needs a re-arm the harness allows. The bridge is unwatched until the next tap-in.
- Mancini fetch: today's 06:58 blob (10-01) was a 683-char non-letter and was skipped correctly. st-znw6 is still in progress.
- Carried in_progress (untouched): st-8l4k, st-8qqw, st-92m7, st-9r51, st-c6ii, st-fsf3, st-gnv5, st-x3tx, st-znw6, st-2nyb, st-3qio, st-5n3s, st-9dyz, st-eww7, st-g0jo, st-ow3p, st-q9re, st-v6p5, st-ygy1.
- Research, not started: st-peqp (large-lot definition); PIVOT_FILTER_TICKS calibration.

**Tried**:
- The push hold was carried for 3 days as a status line ("held behind st-5n3s review group"), never asked → Steve: "those needed pushed, didn't they?" A hold must be put to him as a one-line ask, not inherited.
- Monitor caps at 30 min, so the bridge watch woke the session every 30 min → `--until-event` under Bash run_in_background (2h). The 2h kill notice says not to restart at max timeout, so the re-arm loop does not work as designed.
- Stop-outs 12:47 and 14:32 (P7680, -$31.30 / -$41.30, 9 s and 5 s): the entry paid the ask, the stop was struck from the fill but triggers on MARK, so the real room was the distance minus half-spread minus drift. The preview took ~1 s of 3 s click-to-fill and was a contributor, not the cause.

**Files Changed**:
tools/bridge_inbox.py
tests/tools/test_bridge_inbox.py
.claude/skills/tap-in/SKILL.md
execd/ (orderform, orderpage, service, schwab, paper, bounds, bounds.example.yaml, panel, README, view log)
strader/intent/execd.py
deploy/install.sh
deploy/systemd/ (execd units: view-log dirs)
docs/execution-engine-operations-manual.md
tests/execd/ (incl. scenario/test_sequences.py, test_page_flow.py, conftest.py)
docs/a2a/inbox.md
runbook/mancini/ (parsed/charts for 2026-10-01, via run.py)

---

