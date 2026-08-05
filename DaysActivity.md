# DaysActivity - 2026-08-05

## 14:35 - Session Handoff [Capture Rescue, Mancini Parse, Fly Doctrine Corrected]

**Summary**: Found live capture dead 1h49m before the open and rescued it, then installed the supervisor that had been built-but-uninstalled for a day; published the Mancini parse for today; took a direct correction from Steve on fly doctrine and fixed it at the source rather than in memory; ran down a delta claim from 08-04 that turned out to rest on a relationship that does not exist in our data.

**[ALERT] Capture was dead this morning.** `corpus_stream_databento.py` stopped at yesterday's `--until-ct 15:05` and nothing restarted it — no cron launches it, it is a hand-run ritual. Found at 06:41, started 06:45. The desk window *looked* healthy because bridge and feeder were still up from yesterday: the feeder was tailing 08-04's finished file and the bridge still served its 690 bars. That stale-stack trap is the exact failure `st-6qx4` named ("a dead feeder freezes the live page looking like a quiet tape") — now observed, not hypothetical.

**Correction issued to Steve on my own alarm.** I said the tape "was otherwise gone." False. GLBX historical is **$0.00** under the current Databento Futures plan — measured via `--estimate-only` (`metadata.get_cost`, pulls nothing): ES trades and mbp-1 for the gap, and a full settled day (07-31 02:50–15:05), all $0.0000, against an **OPRA control of $6.0663/2h** proving the estimator returns non-zero when it should. So the codebase premise that MBP-1 and live trades are "captured forward or lost forever" is **false for GLBX**. The OPRA half of that asymmetry does hold, so `st-7av4`'s conclusion stands on the surviving half.

**That unblocked the capture-window ruling** Steve had reserved since 07-31. It stopped being a spend question: overnight and evening Globex need no live process, because they backfill free. **Ruled: live capture covers the session only (02:50–15:05 CT); uncovered hours are backfilled.** 24h coverage without asking a long-lived process to survive 24h — which is precisely what failed this morning. `st-6qx4` and `st-btu` both closed; backfill leg filed as `st-wy6u`.

**Fly doctrine — corrected at the source.** Steve caught me framing a setup as "the consolidation range a fly wants to center on." Per claude-monitor, that is at least the fourth correction (2026-05-06, 2026-06-09, 2026-06-24 ×2). Root cause was not recall: **CLAUDE.md** — always loaded, declared authoritative — said "centering butterflies relative to the consolidation range," so instructions outranked the knowledge bundle every session. The bundle's own `Why` note had diagnosed this in July and the source was never fixed. Now fixed: body at the **destination**, delta not theta, precondition is **departure-and-return, not range occupancy**, both entry engines named, banned-framing block in CLAUDE.md and the concept with Steve's three corrections verbatim.

**Delta run-down (the 08-04 "rally bought by nobody" claim).** Tooling cleared, claim demolished. Aggressor convention verified against our own MBP-1 top-of-book — `'A'` printed at/below the bid **100.0%** (16,362 trades), `'B'` at/above the ask **100.0%**, reproduced on a second window; delta is **not** inverted. Both live bridge readings reproduce from the corpus exactly (13:45 → 525 bars/7769.75/−1,453; 14:46 → 593 bars/7783.75/−7,856) — the "discrepancy" I flagged was my own reconciliation error comparing mismatched windows. The finding: ES carries a **persistent positive aggressor tilt**, 17 of 21 days positive, median **+1.11%** of session volume — a baseline that exists nowhere in the codebase, which is why a −0.50% day read as dramatic. And **corr(session delta%, price change) = −0.22 (n=21)** — slightly inverse, effectively noise. Session-scale delta carries no directional edge in our own data.

**GEXBot is live again** — resumed during this session by another party. Collector pid 1669196, 22 polls into `data/corpus/2026-08-05/gexbot.jsonl`. My repeated "no GEX" statements today were true when made and are now stale; auto-memory updated.

**Open Work**:
- `st-e91l` **IN PROGRESS** — intra-bar progressive rendering (the developing bar) is **built, tested, committed, NOT deployed.** Deploy needs a feeder restart, and the feeder re-reads the day file from the start, so the bridge must restart with it or bars duplicate. Run `scripts/live-footprint-up.sh` after the 15:05 stop, then refresh the tab.
- `st-q5xu` (NEW) — **recognizer has no upside mirror.** All four setups are downside forms; there is no failed-breakout. Compounded by every Mancini level entering as `kind=support`, including today's 12 parsed **resistances** (7783…7894). Steve saw `failed_breakdown forming @ 7815 (support ∩ mancini)` while price was rejecting a resistance — same price action, opposite meaning. Two calls needed from him: the mirrored setup's **name**, and whether to apply the interim kind-filter-to-supports (which the acuity path already does). Overlaps `st-tme`.
- `st-wy6u` (NEW) — nightly GLBX backfill. Append is safe for replay (`read_corpus_day` sorts and dedups) but **fatal to a live feeder mid-session** (`build_bars` raises on out-of-order), so it must run after the 15:05 stop. First target is today's own 02:50–06:45 gap, free.
- `st-g63j` (NEW) — delta baseline write-up; re-run as the corpus grows (21 days is one regime, all uptrend). Open question whether the +1.11% baseline belongs on the live footprint so a reading is glanceable against its norm rather than zero.
- `st-i68` — Mancini pre-open cron PATH bug, still open; today's parse was run in-session so it did not bite.
- `st-7av4` — stop the daily OPRA pull; four code sites move together. Now better justified, since OPRA is confirmed at $6.07/2h.
- `st-jfvu`, `st-ndc`, `st-6qx4`, `st-btu`, `st-en7w`, `st-6vi0`, `st-emy5`, `st-frco`, `st-o216` — closed this session.

**Tried**:
- Suspected the aggressor sign was inverted, since a negative delta on a 129-point rally looks exactly like an inversion → **wrong, and the test said so cleanly.** The book-matching check is now written into the measurement doc so the next suspicion re-runs it instead of re-reasoning.
- Flagged a live-vs-corpus data discrepancy → **there wasn't one.** I had compared a 13:00–14:46 live window against a 13:00–13:45 corpus window. Re-deriving both from the corpus reproduced the live numbers to the contract.
- Read the 08-04 gate failure as st-7av4 breakage (OPRA missing from the manifest) → **it was a one-minute timing artifact**: I ran the parse at 06:29, and `corpus_daily` fills the T+1 OPRA leg at 06:30. Waited for the fill and ran with the gate intact rather than passing `--no-gate`.
- Started writing the emissions panel from scratch before reading the working tree → **it was already built** by the tap-in agent running concurrently, which had also committed my in-flight column-marker edit. Cost a duplicate block that had to be deleted. Read the tree before building.
- Two commit/bead bodies were written with unquoted backticks and got **shell-expanded**, silently dropping words from durable records. The `-m "$(cat <<'EOF' ... EOF)"` form is safe; a plain double-quoted string is not.

**Files Changed**:
CLAUDE.md
knowledge/directional-gex-butterflies.md
knowledge/log.md
docs/measurement/cumulative-delta-session-baseline.md
market/orderflow/recognizer.py
scripts/orderflow_drill.py
scripts/orderflow_drill_template.html
scripts/live_footprint_feed.py
scripts/live_footprint_page.py
scripts/drill_bridge.py
scripts/cron/capture-supervisor-session.sh
tools/drill_page_check.mjs
tests/scripts/test_developing_bar.py
tests/market/fixtures/parity/expected_signals_20260702.json
tests/market/fixtures/parity/CHANGES.md
runbook/mancini/commentary/2026-08-05.jsonl

---
