# The Quant Dataset — What We Actually Hold, and What It Unlocks

**Bead:** Quant Dataset Survey (st-nriv) · 2026-08-06 · COO + Strader joint survey
**Trigger:** Steve: "Strader has been unaware of the full extent of the full dataset
we have via the Quant sub… my prompts shouldn't limit your exploration."

## The one-line headline

We hold **one-second-resolution dealer-positioning history** — 15 data
categories × 62 trading days (2026-05-07 → 2026-08-05), ~17,286 snapshots per
category per day, RTH only (08:30–14:59 CT) — **including the orderflow package
nobody knew we were entitled to.** Strader's live poller samples at 60s; the
archive is 60× finer than anything any Strader study has ever used.

## Inventory (measured from the files, not assumed)

Archive: `Z:\Harvest\gexbot-hist\<date>\` — 62 day-dirs, 96 GB, sha256-verified.
Every file is a full-day JSON array of intraday snapshots. Cadence measured on
2026-08-04: median gap 1s, max 3s, first snapshot 08:30:02 CT — the feed is
RTH-only, confirmed in the data.

| Package.category | Per-snapshot content (measured keys) | Day size |
|---|---|---|
| `state gex_full/zero/one` | spot, zero_gamma†, major_pos/neg × vol/oi, sum_gex vol/oi, delta_risk_reversal, max_priors, per-strike rows (~71 rows 0DTE, ~108 full) | 60–92 MB |
| `state delta/gamma/vanna/charm × zero/one` | spot, major_positive/negative, major_long/short_gamma, per-strike `mini_contracts` rows (~71) | 59–65 MB |
| `classic gex_full/zero/one` | same shape as state gex; **zero_gamma populated here** | 72–109 MB |
| `orderflow` | 37 scalar fields/snapshot: agg/net DEX (call/put split, 0DTE + 1DTE), gexoflow, dexoflow, cvroflow, zcvr/ocvr, zgr/ogr, zvanna/ovanna, zcharm/ocharm, mcall/mput majors, ml/ms gamma | 12 MB |

† **Schema landmine (measured 2026-08-04):** `zero_gamma` is populated in the
**classic** package only (17,285/17,286 snapshots nonzero); the **state**
package writes 0 there all day. State's flip lives in its gamma category's
`major_long_gamma`/`major_short_gamma`. This is almost certainly the root of
the distiller's dead zero_gamma path (st-roj9). Any regime join must read the
right package.

**Settled by measurement (2026-08-06, this survey):**
- Strikes row = `[strike, gex_by_volume, gex_by_oi, [5 prior values]]` —
  proven by summing columns against `sum_gex_vol` / `sum_gex_oi` (exact match).
- For SPX, `sec_min_dte` = 1 on every sampled day: with daily SPX expirations,
  `_one` categories are genuinely 1DTE here, mooting the vendor's
  ordinal-vs-1dte doc inconsistency for our ticker.

**Still unknown (vendor publishes nothing):** `mini_contracts` row semantics
(`[strike, a, b, c, [3 values], n, null]`), `max_priors` (six-lookback reading
is plausible but unconfirmed), and **all 34 orderflow scalars** — not one
carries a definition in the spec, README, WebSocket doc, downloader, or the
principals' Discord archive. Meaning must come from empirics or a direct
vendor question.

## What the vendor documentation adds (full survey: `vendor-docs-survey-2026-08-06.md`)

The distilled load-bearing findings from the vendor-docs pass:

- **Quant is a superset tier.** Every Classic/State/Orderflow endpoint carries
  the Quant tag — the orderflow entitlement is bundled by design, not an
  accident. Quant-exclusive: `/hist`, the WebSocket feed, `/tickers/quant`,
  `/options/{ticker}/expiries`.
- **Classic vs State is methodology, not redundancy** (principals' Discord,
  canonical tier): Classic increments unsigned volume naively; State
  classifies each trade buy/sell against a vol surface and accumulates
  *signed* customer positioning. Classic is the methodological control.
- **`full`/`zero`/`one` defined:** 90-day aggregation / next expiry+0 / next
  expiry+1. The live category roster (queried 2026-08-06) exactly matches our
  17-combo archive — we hold everything the vendor publishes for SPX.
- **Cadence ceiling is vendor-stated:** "Data is not updated more than once
  per second… not more than 1 request/second per ticker per metric"
  (AGENTS.md). Our 1s archive is the feed's native resolution.
- **/hist retention is a 90-day rolling window.** Days age out permanently;
  our Z: archive is the only durable copy of anything older.
- **WebSocket (Quant-only): the sharpest live-vs-hist asymmetry.**
  Zstd-compressed protobuf over Azure Web PubSub, 6 hubs, 150-group cap —
  and **explicit-expiry groups** (e.g. `SPX_state_gamma_20260717`, ~5s
  cadence) exist ONLY live: "not persisted to REST history." Per-expiry greek
  surfaces are unrecoverable after the fact. If per-expiry structure ever
  matters (pin risk on a specific weekly, OPEX mechanics), it must be
  captured live during the Quant month or lost.
- **Our canonical spec copy is stale:** vendor is at v2.3.0 (adds a separate
  `research` product/key, new endpoints, new negotiate flow); archive schemas
  are unchanged between 2.2.0 and 2.3.0. The 2.3.0 copy is saved alongside;
  refreshing the canonical file is an explicit decision per the
  canonical/community/measured separation.
- **Client hardening notes:** the vendor's own downloader sniffs gzip magic
  bytes rather than trusting headers (explains our plain-JSON `.gz` files);
  `User-Agent` and `Accept` are required on every request; auth-scheme docs
  self-contradict (Bearer vs Basic) — our working poller config is the
  authority.

## What this makes possible — the leverage map

Ordered by nearness to money, not by novelty.

### 1. Retro Gamma Cut (st-trbn, deferred → now fully unblocked)
The bead the harvest was for. Join 353 recognizer confirms (acuity run 2)
to gamma regime **at confirm second** — not at the nearest minute. Win rate by
regime cell vs the 47% baseline. This answers "how much better is the
recognizer with GexBot context" with measurement, and the 1s cadence removes
the timestamp-slop objection entirely.

### 2. Orderflow × flush detection (st-g3yh / st-863b / st-88ei)
The orderflow package is a per-second DEX/GEX flow record we have **never
consumed** (st-fyey wanted to start collecting it — it turns out we already
hold 62 days retroactively, including the 07-22 and 07-31 flush days the
watcher-validation bead needs). Question the data can now answer: do
`net_dex` / `dexoflow` / `cvroflow` lead price into flushes, and by how many
seconds? If the lead is real, the flush watcher gains a confirming (or
arming) input that is orthogonal to the meter.

### 3. Regime context for every lane, retroactively (st-lstj, st-roj9, st-rtuu)
Every historical study Strader has run (Mancini level performance, obvious-line
thresholds, day-shape spread) can be re-cut by gamma regime, distance-to-flip,
and wall position — per second, for 62 days — without waiting a single forward
session. The distiller V2 rewrite (st-roj9) gets its regime definitions fixed
by the classic/state finding above.

### 4. 1DTE structure recovered (st-8ywx)
Live capture drops the 1DTE legs; the archive holds every `_one` category for
62 days. Charm/vanna decay structure into expiry — the mechanics behind
late-day pin/unpin — is sitting in `state_charm_one`/`state_vanna_one`
unexamined.

### 5. Level-confluence measurement (Mancini × walls)
Mancini levels now have a per-second record of whether they coincided with
GEX walls (`major_pos/neg`), and whether wall-coincident levels held more
often. The level-state tracker (st-qih1) writes touched/held/broken/reclaimed
with evidence; joining wall distance at touch time is a small script, not a
project.

### 6. Forward collection strategy (st-p3lv, st-fyey)
The /hist archive IS the 1s record, published next day. Live polling therefore
only needs to serve **real-time** consumers (distiller, watcher) — research
never needs a forward collector at high cadence. This reframes st-p3lv: the
supervised forward-collection service is for live-decision latency, not corpus
completeness, and st-fyey's "capture orderflow, data first" is already
satisfied backward by the archive + nightly backfill sweep going forward.

## Operational notes

- **Downgrade clock:** Quant is a one-month sub (decision ~Sep 1). The archive
  through Aug is already ours; a nightly/weekly `gexbot_hist_backfill.py` run
  (archive-aware, proven idempotent) keeps extending it at near-zero cost
  until the tier decision. That decision should be made against this survey.
- **Storage:** the files are plain JSON mis-named `.json.gz` (st-kr4a) — the
  API's gzip was transparently decompressed at download. Recompressing the Z:
  archive would take ~96 GB → roughly 15–20 GB. Worth doing once the naming
  fix and readers agree on a convention.
- **RTH-only:** no overnight dealer-positioning exists in this feed. Overnight
  lanes (Mancini overnight brief, ETH flush study) cannot lean on it.

## Proposed next actions (for discussion, not yet beads)

1. Undefer **st-trbn** and run the retro gamma cut — days of work, the payoff.
   Regime source per the landmine finding: `classic_*` for `zero_gamma`, or
   state gamma majors — decided explicitly, not assumed.
2. A short **orderflow-lead study** on the two known flush days — does DEX
   flow lead the tape? Cheap, high information, and it doubles as the
   empirical decoding pass the 34 undocumented scalars need anyway.
3. Fix the schema landmine trio together: st-roj9 (distiller regime source),
   st-kr4a (naming/compression), st-8ywx (1DTE in live capture) — they are
   all "read the right field from the right package" issues.
4. Extend the backfill cron through the Quant month (90-day rolling window:
   what we don't archive, we lose); fold the tier-downgrade decision (~Sep 1)
   into a review of what these studies actually used.
5. Decide whether **explicit-expiry live capture** is worth standing up during
   the Quant month — it is the one dataset that cannot be recovered later,
   and the decision has a hard expiry if the tier downgrades.
6. Send the vendor the orderflow field-definition question — a paid
   entitlement shipped with zero documentation earns the ask.
