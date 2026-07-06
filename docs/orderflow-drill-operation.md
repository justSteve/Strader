# Orderflow Drill & Session Review — Operator's Guide

*st-yfn / st-6b0 · updated 2026-07-06. The one-page answer to "how does this apparatus work?"*

## What this is

Three connected pieces. The **corpus** records every ES trade of every session (08:30–15:00 CT daily, automatic). The **engine** (`market/orderflow/`) turns that stream into deterministic structure — volume bars, footprints, and signals. The **drill** and **session review** are the two human surfaces: the drill replays any recorded day for screen-time training; the review couples a day's replay to Mancini's letters about it. Everything downstream of the corpus is replay-exact: the same day always produces byte-identical bars, signals, and drills.

## How a day becomes a drill

1. The daily pull lands the session's trade tape (time & sales with exchange-tagged aggressor side) in `data/corpus/<date>/`.
2. The replay reader dedups and sorts it into canonical order (event time, then venue sequence).
3. The bar builder closes a **volume bar every 2,000 contracts** — bars measure market effort, not clock time. A bar's footprint records, at each 0.25 price, how much volume was buyer-aggressive vs seller-aggressive.
4. The drill generator embeds those bars in a self-contained HTML page. Nothing in the page contacts anything; it is the day, frozen.

## The drill screen, top to bottom

- **Header** — symbol, date, contracts-per-bar, bar count; legend (blue = buy aggression, red = sell aggression, outline = POC).
- **Controls** — Play/pause · step back/forward · Speed (1× real time to 240×) · seek slider · Level box + Arm · level chips · **Rows** (Compact/Medium/Large cell height; Compact hides numbers, doubles visible price range) · **Cells** (what the cell text shows: **Δ** signed delta [default], **Volume** total, **bid×ask** raw pair) · Table view · **?** (help overlay).
- **Readouts** — current bar #, clock, last price, bar Δ, **Session Δ** (running sum — watch its trend, not its level), bar duration, drill score.
- **The chart** — one column per bar. Each cell: color = which side was aggressive, intensity = how much traded, text = per the Cells mode; hover any cell for the full breakdown. Outlined cell = the bar's POC. **Dashed empty cell** = price jumped that level without one trade (micro-LVN, real information). Column footer = bar delta + closing time. Armed level = dashed red line.
- **Pace strip** — seconds each of the last 60 bars took. Short bars = urgent tape. Time is an *output* here.
- **Hints line** — keyboard (Space, ←/→) and the three **highlight jumps**: *fastest tape*, *biggest Δ bar*, *sharpest Δ flip* — each seeks to a computed moment with a caption saying why it matters.

## The two drill modes

**Pace acclimation.** Press Play. Bars arrive at their real recorded rhythm compressed by the speed setting. The goal is bodily calibration: what urgent vs dead tape *feels* like when bars, not minutes, are the unit.

**Guess-then-reveal.** Click a chip (session levels, or **M:** chips = numbers harvested from Mancini's forecast letter) or type a price and Arm. You're dropped ~10 bars before price first visited that level, with a caption; the **Visits** row lists every approach that day. Play the lead-up. Within ~1 point of the level, the replay pauses and asks: **Reject or Accept?** Answer; the tape resumes and judges you — 4 points through the level = accept, 4 points rejected away = reject, neither within 10 bars = chop (no credit). Every call logs below with a running score (stored per-day in the browser, exportable as JSON).

The question behind every rep is the **force-and-effect compass**: force *with* effect = healthy continuation · force *without* effect = absorption, someone big disagrees · effect *without* force = hollow move, reversal candidate.

## Session review

```
.venv/bin/python scripts/session_review.py --date 2026-07-02
```

One page per day: the **forecast letter** (last one published before the open — was he right?), the **retro letter** (first after ~13:30 CT — his own recap), explicit banners for anything missing (no letter, partial tick coverage + the ~$0.51 backfill quote), the harvested candidate levels, and the button into that day's drill with M: chips loaded. Letters cache locally after first fetch; 330 letters (June 2025 →) are available.

## Under the hood, already running

The engine computes more than the drill yet displays: session-anchored **CVD** (untagged prints bucketed separately, never faked into delta), **sweeps** (one aggressor walking ≥3 levels, ≥100 contracts, sub-¼-second — ~39/session), **large lots** (≥100 contracts and ≥10× the rolling median print — ~33/session), **delta divergences** at confirmed swing pivots (~97/session), per-bar **diagonal imbalances** (~333 levels/session), and the **prior-session volume profile** (POC/HVN/LVN as levels — on 7/2 the math's POC 7510 and LVNs 7491/7541 landed on Mancini's 7511/7492/7541). These become visible in the drill when the four-beat **setup recognizer** (st-2kf) lands and starts saying "failed breakdown forming at your level" with its evidence attached.

## Commands

| Do | Command |
|---|---|
| Drill for a day | `.venv/bin/python scripts/orderflow_drill.py --date <YYYY-MM-DD>` |
| Full review (letters + drill) | `.venv/bin/python scripts/session_review.py --date <YYYY-MM-DD>` |
| Finer/coarser bars | add `--bar-n 1000` (etc.) |
| All engine tests | `.venv/bin/python -m pytest tests/market/orderflow -q` |
