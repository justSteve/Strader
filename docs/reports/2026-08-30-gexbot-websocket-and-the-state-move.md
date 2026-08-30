# The GexBot WebSocket, and what the State move actually costs

*2026-08-30 · Strader · bead st-qcj3 (Quant To State Move) · your ruling: cancel Quant,
move to State. Cancellation confirmed executed in the portal and easily reversed;
access runs **through 2026-09-06**.*

Every figure below is measured — from the vendor's own spec and docs in
`docs/gexbot/`, or from our own capture on disk. Where nothing has been
measured, it says so.

---

## The short answer

**The WebSocket cannot be bought on its own.** All three `/negotiate` methods —
`POST`, `PATCH`, and the deprecated `GET` — are tagged `['Quant']` and nothing
else in the vendor's spec. There is no WebSocket add-on, no Classic+WS, no
State+WS. So "is the WebSocket worth considering" is not a question about the
WebSocket's price; it is the question of whether the WebSocket alone justifies
the Quant premium over State, once the Orderflow indicator is off the table.

**On the measurements below, no — not on six days of evidence.** The feed
would demonstrably improve the *record* we keep. Nothing measured shows it
would improve a *trade*. Recommend proceeding with the cancellation as ruled.

**But the ruling has a second half you did not ask about, and it is the
expensive one.** `/hist` is Quant-only too. From 2026-09-07 no GEX day can ever
be backfilled again — a collector outage becomes a permanent hole, forever.
That is the thing worth spending the last six days on, and §5 is the checklist.

---

## 1. What State actually keeps and loses

The tiers are **cumulative, not disjoint** — this is the spec's own tag table,
which is the authoritative entitlement map. Every endpoint, every tier that
grants it:

| Endpoint | Tiers that grant it |
|---|---|
| `/{ticker}/classic/{category}` (+ `/majors`, `/maxchange`) | Classic, **State**, Orderflow, Quant |
| `/{ticker}/state/{category}` (+ `/majors`, `/maxchange`) | **State**, Orderflow, Quant |
| `/{ticker}/orderflow/{category}` | Orderflow, Quant |
| `/hist/{ticker}/{package}/{category}/{date}` | **Quant only** |
| `/negotiate` (POST · PATCH · GET) | **Quant only** |
| `/tickers/quant` | **Quant only** |
| `/options/{ticker}/expiries` | **Quant only** |
| `/tickers`, `/{package}/categories` | Public (no auth) |

**State keeps everything on your charts.** The full classic GEX ladder
(`gex_full`, `gex_zero`, `gex_one`), the full state greek ladder
(delta/gamma/vanna/charm × zero/one), and the `majors` endpoint that produces
`major_positive` / `major_negative` / `major_long_gamma` / `major_short_gamma` —
the magnet levels themselves. Nine of the ten legs our 60-second poller collects
survive the move untouched.

**State loses four things.** The orderflow package (the tenth leg, and the 1 Hz
capture), `/hist`, the WebSocket, and the two Quant discovery endpoints.

One factual note, not a recommendation: **Orderflow is its own purchasable
tier**, separate from Quant. If you ever wanted the orderflow metrics back
without `/hist` and the WebSocket, that is the door. The vendor publishes no
prices in any retrievable document, so I cannot tell you what it costs.

---

## 2. What the WebSocket would actually deliver

Six facts from the vendor's own material:

1. **It cannot be fresher than 1 Hz.** The vendor's ceiling, stated once, in
   `AGENTS.md` and nowhere else: *"Data is not updated more than once per
   second."* The WebSocket does not beat that — it removes the *round trip*, not
   the recompute interval.
2. **RTH only.** *"Data is only published during New York Stock Exchange cash
   hours"* — 08:30–15:00 CT. No overnight, no pre-market.
3. **Transport is Azure Web PubSub; payloads are Zstandard-compressed Protocol
   Buffers — and the vendor does not publish the `.proto` schema** in either of
   its repos. Decoding means using their reference client
   (`nfa-llc/quant-python-sockets`) or reverse-engineering the wire format.
   That is the build cost, and it is the reason this has sat unwired for 25 days.
4. Six hubs, groups named `{ticker}_{package}_{category}`, **150 groups** on a
   standard key. Far more than SPX needs.
5. **Explicit-expiry groups** — per-expiry greek surfaces — are WebSocket-only
   and are *never* persisted to `/hist`. Unrecoverable after the fact. But they
   publish on a **~5-second** cadence, slower than the standard groups, and for
   SPX 0DTE the `zero` and `one` ordinals already give you the front expiry and
   the next. For what you trade, this adds close to nothing.
6. A successful negotiate closes any existing connection on the same slot — one
   live consumer at a time.

---

## 3. What we measured on our own capture

The interesting question is not what the spec promises but what we are actually
missing today. One RTH session, 2026-08-27.

**The 1 Hz orderflow poller is not running at 1 Hz.**

| | |
|---|---|
| Polls in the session | 14,487 |
| Polls that returned a **distinct** vendor timestamp | **14,487 — every one** |
| Median spacing between our polls | **2.0 s** (mean 1.62 s) |
| Spacing distribution | 1 s ×6,058 · 2 s ×8,007 · 3 s ×364 · 4 s ×51 · 5 s ×6 |
| Session span | ≈ 23,470 s |

Read those two rows together. We never once got a stale repeat — the vendor
genuinely has new data every time we ask. But our poller enforces 1.1 s
end-to-start *plus* the request round trip, so we land every ~1.6 s on average.
At the vendor's 1 Hz ceiling there were roughly **23,470 updates published and
we captured 14,487** — we are seeing about **62%** and missing about **38%**.

A push feed closes exactly that gap, because there is no round trip to pay for.

**The greek ladder is sampled far too coarsely to know what it is doing.** The
state package polls at **60 seconds** — 301 samples in the session. How often
each major level differs from the previous sample:

| level | changed | of 300 intervals | distinct values |
|---|---|---|---|
| `major_positive` | 50 | 17% | 21 |
| `major_negative` | 77 | 26% | 31 |
| `major_long_gamma` | 150 | **50%** | 66 |
| `major_short_gamma` | 137 | **46%** | 72 |

A series that differs from its previous sample half the time is a series your
sampling rate cannot resolve. We cannot currently tell a real level migration
from whatever happened in the 59 seconds we did not look at — and when
`major_positive` moves, we learn about it up to a minute late.

**That is a data-quality finding, not a trading one, and the distinction is the
whole answer.** Nothing in the corpus shows that a one-second GEX ladder would
change a fly entry or a singles exit. You read the magnet late in the day and
center on it; a level that settles 21 distinct values across a session is one
you read once. Six days is not enough time to measure whether the other 38%
carries anything, and I would not spend the tier on the hope that it does.

---

## 4. What `/hist` is worth, and why it is the real cost

`/hist` is Quant-only. On State there is no historical GEX at any price: no
backfill, no second chance, no way to recover a day a collector missed. Since
GEX history for this desk begins **2026-08-05** and nothing exists before it,
every forward day becomes irreplaceable the moment the tier drops.

Three things measured today:

1. **The archive is complete.** 79 days held across `data/corpus/gexbot-hist`
   and `/mnt/z/Harvest/gexbot-hist`, spanning 2026-05-07 → 2026-08-28 — that is
   **63 of the 65 weekdays** in the current 90-day window, and the two absent
   dates (2026-06-19 Juneteenth, 2026-07-03) are market holidays for which the
   vendor itself returns no file, on every one of 84 attempts. Sixteen of the 79
   days have already aged out of the vendor's window; we hold them anyway.
2. **`/hist` is not gated by subscription period.** The backfill successfully
   pulled days from inside the 2026-07-03 → 2026-08-05 subscription pause. The
   90-day window is the vendor's archive, not a record of what you paid for. So
   the whole window is reachable right up to the cutoff.
3. **The nightly harvest is fragile in a way that now matters.** It runs on
   plain cron (`0 21 * * 1-5`), not a systemd timer, so a powered-off 21:00
   silently loses the run — it missed **2026-08-27 and 2026-08-29** in the last
   two weeks. That is the same defect that made cron skip four of seven Saturday
   corpus pulls before that job moved to a timer. With five nightly runs left,
   each miss is a permanently lost day. **2026-08-28 was unharvested when I
   looked; it is on disk now.**

---

## 5. The six days, in order

Nothing here needs a decision from you. It is on **st-qcj3 — Quant To State
Move** and I will run it.

**Before 2026-09-06**

1. **A final `/hist` sweep by hand on 09-05 or 09-06. This is mandatory, not a
   backstop.** The last session under Quant is Friday 09-04; `/hist` publishes
   T+1; the nightly cron is `0 21 * * 1-5`, so the Friday run harvests through
   09-03 and 09-04's own data does not exist yet when it fires. There is no
   weekend cron. **The nightly cannot reach the last session of the entitlement
   by construction** — only the hand sweep can, and 09-06 is the last day the
   endpoint answers.
2. Move the nightly off cron onto a timer with `Persistent=true`, or treat all
   five remaining runs as best-effort. Two of the last fortnight's runs were
   already lost to a powered-off 21:00 (08-27, 08-29).
3. Let the last Quant sessions' 1 Hz orderflow capture run out normally — it is
   the last of that data this desk will ever hold.

**On 2026-09-07, after the drop**

4. Flip `gexbot_orderflow_1s` and `gexbot_hist_archive` in
   `config/entitlements.yaml` from expect-present to expect-absent, or the probe
   alarms every day forever. The orderflow entry's own note already says *"if
   this goes permanently quiet inside RTH, suspect the tier before the code"* —
   on State that becomes the correct steady state.
5. Drop the `/SPX/orderflow/orderflow` leg from the ten-endpoint package poller
   and stop the 1 Hz orderflow collector. (It auto-skips on entitlement, so
   nothing breaks if this slips — it just runs and logs nothing.)
6. **What State bills** is still unrecorded — the one open registry question.
   The cancellation itself is confirmed executed and reversible.

---

## 6. If you ever reconsider

The one thing that would make this decision on evidence rather than on a spec is
a single recorded session of the WebSocket feed at 1 Hz on the greek ladder,
sitting beside the same day's 60-second poll — then the question "does the other
38% carry anything" is a measurement rather than an argument. It is roughly half
a day of build against an undocumented protobuf schema, and it has to happen
before 09-06 or not at all.

I do not recommend it now. The build risk is the undocumented part, the payoff
is unmeasurable inside six days, and the `/hist` sweep is the thing that is
actually irreversible. Say the word if you want it anyway and it goes ahead of
everything else on the bead.
