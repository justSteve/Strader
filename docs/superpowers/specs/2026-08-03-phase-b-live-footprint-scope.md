# Phase B — Live Footprint: Scope

*Bead st-d5f (Orderflow 8 of 8) · drafted 2026-08-03 · the gate cleared today*

**Terms used below.** *RTH* is regular trading hours, 08:30–15:00 CT. *Globex* is
the overnight futures session, 17:00 ET Sunday through Friday afternoon. *MBP-1*
is market-by-price level 1 — the top of the order book, bid and ask size, which
is what lets us see size being *refilled* rather than just traded. *Trades* is
the time-and-sales tape. Absorption needs both; the footprint needs only trades.

---

## 1. Where we actually stand

The blocker on `st-d5f` was written as *"BLOCKED until the 8/1 DataBento CME
Standard upgrade."* **That upgrade is live and verified.** A live `GLBX.MDP3`
session was accepted at 01:06 ET today and returned real ES trades
(7562.75 × 5, 7563.00 × 1). Seven of the eight orderflow beads are closed;
this is the last one.

What that does **not** mean is that anything is flowing. Verified again at
08:54 CT: no streamer process, no cron entry, nothing listening. The
subscription is being paid for and is delivering to nobody.

| Piece | State |
|---|---|
| CME Standard live entitlement | ✅ verified today |
| Live capture running | ❌ nothing |
| Live footprint renderer | ❌ never built — fenced off as Phase B |
| Absorption `refill_events` | ⚠️ **fully built**, no quote source |
| Replay footprint surface | ✅ works, corpus-fed |
| Live/replay parity harness | ✅ closed (st-bw9) |

The parity harness matters more than it looks. The spec's §5 guarantee is that
the engine proven on replay is byte-for-byte the engine that goes live — so
none of Phase A is throwaway, and going live is a *feed* problem, not an
*engine* problem.

---

## 2. The four pieces of work

### 2a. Point the streamer at ES — small

`scripts/corpus_stream_databento.py` is closer to done than its own docstring
admits. It already has: per-dataset worker threads with independent reconnect
handling, an `"es"` stream spec writing to `databento_glbx_es.jsonl`, the
lossless raw-DBN tee, and `--start-ct` / `--until-ct` / `--max-ticks` controls.

Three gaps, all modest:

- **The docstring is now false.** It says *"ES (GLBX.MDP3) is NOT subscribed for
  live"* and *"Requesting `--streams es` would stream live GLBX at
  pay-as-you-go rates; don't."* That warning was correct on 2026-06-08 and is
  wrong today. Leaving it there is how someone talks themselves out of the
  thing we just bought.
- **One schema for all streams.** `--schema` (default `trades`) is applied to
  every spec, so trades and MBP-1 cannot run together. Phase B needs both.
  `default_specs()` should yield an es-trades and an es-mbp1 spec as separate
  workers — the threading model already supports it, since each worker owns its
  own client and file handle.
- **Window.** Default is 13:00–15:00 CT. Phase B wants round-the-clock.

### 2b. Live bar feed into the page — medium, smaller than it sounds

The drill template is **not** a static artifact that needs replacing. It
already speaks to a local server: it POSTs snapshots to `drill_bridge` on
`127.0.0.1:7788/state` and polls `/commands` on a 2-second cadence, and it
already renders bars progressively with intra-bar fill timers rather than
popping in completed bars.

What is baked is only the *source*: `orderflow_drill.py` substitutes a JSON
payload into a marker in the HTML at generation time. The live work is swapping
that source for a bridge-fed stream of bars as they close — reusing the polling
channel and the fill animation that already exist. This is an extension of a
working surface, not a new one.

### 2c. Absorption activation — nearly free once quotes flow

`market/orderflow/absorption.py` is complete. `_Episode.observe_size()`
increments `refill_events`; `_close()` gates on `ABSORPTION_REFILL_MIN` and
scores against `ABSORPTION_REFILL_SCALE`. It consumes `BookEvent` and has never
had a live book to consume. Once MBP-1 flows, this lights up and the
"trades-only, degraded" label comes off the absorption scores.

### 2d. Round-the-clock capture resolves `st-btu` for free

`st-btu` asks whether live capture needs a pre-market window. Its evidence is
one day for and one day against:

- **For (7/22):** Mancini's marquee Failed Breakdown printed 07:56:53–07:56:57
  CT at 7504.0 — 34 minutes before the RTH window opens. The recognizer saw
  only the RTH echo at 7533.
- **Against (7/24):** that day's marquee setup printed 08:45–09:05 CT, inside
  coverage.

The spec already anticipated this: *"Overnight (Globex): skip for the interim;
Phase B's round-the-clock capture makes it moot."* Capture round-the-clock and
the question stops needing an answer. This also closes the gap I flagged
overnight — **nothing currently captures Globex at any hour**, because the batch
ES puller runs 08:30–15:00 CT and the live streamer defaults to 13:00–15:00 CT.

---

## 3. What it costs in disk

Measured from real corpus days, RTH only:

| Stream | Per RTH day |
|---|---|
| ES trades | ~142 MB |
| **ES MBP-1** | **1.6 – 2.9 GB** |
| OPRA trades | ~171 MB |

MBP-1 is the entire storage story; everything else is rounding. Current headroom
is 824 GB free with the corpus at 92 GB. At ~3 GB/day that is roughly nine
months of RTH-only capture, and round-the-clock plausibly cuts that to three or
four.

The mitigation already exists and is not wired up:
`scripts/corpus_compact_databento.py` zstd-packs the DBN archive and gzips the
JSONL, and no compacted artifact exists in the corpus today. **Compaction should
land with Phase B, not after it** — turning on round-the-clock MBP-1 without it
is how the disk becomes a problem in a quarter rather than a year.

---

## 4. Three decisions that are yours

1. **Capture window.** Round-the-clock, or RTH plus a pre-market extension?
   Round-the-clock is the spec's own answer and moots `st-btu`; it also costs
   the most disk. This is the one that changes everything downstream.
2. **Does the live footprint replace TradingView's?** The spec frames Phase B as
   *"our own live-capture footprint replaces TV's."* That was written before we
   knew the agent cannot read your TV charts. Worth deciding deliberately
   whether ours becomes your watching surface or runs alongside for a while —
   ours has the advantage that I can see it too.
3. **The held pre-build spend.** You held ~$4 of metered historical-quote pulls
   on 2026-07-08 pending drills and hardware. Live capture supersedes the need
   for it, so I read that hold as moot rather than pending — confirm.

---

## 5. Why this is time-sensitive, and it is not the sunk cost

The spec's §2 note: **quotes are never backfilled.** MBP-1 is captured forward
from the live tee or not at all. Every session that passes without live quote
capture is a day of book data that cannot be bought later at any price — unlike
trades, which we can and do pull T+1.

That is the real argument for moving, and it is stronger than the subscription
being idle. The subscription is a recurring cost you are already paying; the
quote history is the thing that is actually being lost.

---

## 6. Recommended sequence

| # | Step | Why first |
|---|---|---|
| 1 | Correct the streamer docstring; add es-trades + es-mbp1 as separate specs | Smallest change, unblocks everything, removes a false warning |
| 2 | Wire compaction to a T+1 cron | Must precede round-the-clock, not follow it |
| 3 | Start round-the-clock ES capture under supervision | Long-lived process — a cron tick is the wrong shape; needs a supervised service |
| 4 | Activate absorption on the live book | Nearly free once step 3 runs |
| 5 | Bridge-fed live bars into the drill surface | The visible payoff, and the piece that most benefits from real tape to build against |

Steps 1 and 2 are self-contained and safe to do before any ruling on the window
— they are true regardless of which way you decide. Step 3 is where your
capture-window answer binds.

**One caution on step 3.** A round-the-clock streamer is a long-lived process,
not a scheduled script, and everything in this repo's automation is currently a
cron tick. That is the genuinely new operational shape here, and the most
likely source of silent failure: a streamer that dies at 02:00 and is noticed at
08:30 has cost a night of unbackfillable quotes. Health-alerting on it should
land in the same step, not later.
