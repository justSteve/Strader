# Recognizer Acuity Run 2 — LEG B: Precision + Forward Excursion, Corpus-Wide

**Bead:** st-n62 · **Run:** `20260727T054148Z` · **Date:** 2026-07-27
**Data:** `data/measurement/acuity-run2-{days,confirmations}.jsonl` (append-only; filter on the run id)
**Code:** `scripts/acuity_run2.py` at the commit tagged in this file's git history

## Question

Run 1 (st-3vu, `score_recognizer.py`) asked *sensitivity*: does the machine confirm
where Mancini said an event happened, on his showcase days. This run asks
*precision*: of everything the machine confirms, how often does price then
actually go — measured mechanically, corpus-wide, on ordinary days included.

## Method

- **Universe:** every corpus day with ES tape — 262 candidates, **179 scored**
  (83 skipped: no anchors derivable — no labels, no letter, no prior corpus day
  for a profile). 26 scored days have full-RTH tape; 153 are late-day pulls
  (13:00–15:00 CT), which is our trading window anyway.
- **Anchors (what trading would actually have):** the day's Mancini levels —
  labeled corpus (63 days) else parsed morning letter (8 days) — plus up to 6
  support-side **LVNs from the prior session's volume profile** (all days with
  a prior day on disk). All anchors are supports → **every recognition is
  bullish-biased**. Read every number below as "accuracy of bullish reversal
  confirms."
- **Grade per confirmation:** entry = first trade at/after the confirm bar;
  MFE/MAE (points) over the next 15/30 minutes; first-touch verdict at **±5 ES
  points** (win = +5 prints before −5). Symmetric and strict — a confirm that
  eventually ran 15 points but took 5.5 of heat first grades `loss`.

## Overall

| Metric | Value |
|---|---|
| Confirmations | **353** across 62 days (117 scored days produced zero) |
| First-touch ±5 @ 30 min | **47%** (149W / 169L; 35 undecided) |
| First-touch ±5 @ 15 min | 47% |
| Median MFE / MAE @ 30 min | 6.75 / 6.50 pts |
| MFE > MAE (edge dominance) | 50% |
| Episode confirm rate | 72% (353 confirmed vs 139 invalidated) |

**Headline: unfiltered, the recognizer's confirms are a coin flip.** It is a
*detector*, not a filter — it confirms readily (72% of opened episodes) and the
raw stream carries no mechanical edge at ±5 symmetric. The edge appears the
moment you cut by regime:

## Cuts

### Day type (TPO shape, full-day) — the dominant pattern

| Shape | n | Win | Med MFE/MAE |
|---|---|---|---|
| **P (trend up)** | 60 | **65%** | **9.4 / 4.5** |
| D (rotation) | 216 | 47% | 6.5 / 6.1 |
| **b (trend down)** | 77 | **32%** | 6.0 / 8.5 |

Bullish reversal confirms work when the day's auction is already leaning up,
break even in balance, and get run over on trend-down days. This matches
doctrine (P/b = trend day, flies at risk) — but note the **lookahead caveat**:
full-day shape isn't knowable at confirm time. The live filter must use the
*developing* shape (classification-so-far at the confirm bar). Building that
gate is the single highest-leverage follow-up.

### Hour of confirm (CT)

| Hour | n | Win | Med MFE/MAE |
|---|---|---|---|
| 08 | 42 | 52% | 17.2 / 9.1 |
| 09 | 59 | 48% | 8.8 / 10.2 |
| **10** | 20 | **26%** | 4.8 / 7.8 |
| 11 | 26 | 48% | 6.5 / 6.4 |
| **12** | 20 | **20%** | 2.5 / 9.5 |
| 13 | 80 | 48% | 5.5 / 6.5 |
| **14** | 106 | **53%** | 5.1 / **4.0** |

Midday (10:00, 12:00) is where confirms go to die — 20–26% — which
independently validates the playbook's 10:00–13:00 no-trade window. The
14:00 hour is the largest bucket and the best risk profile (median MAE 4.0).
The open hour wins less often than it moves (huge MFE *and* MAE).

### Setup type · anchor source · coverage

| Cut | n | Win | Note |
|---|---|---|---|
| level_reclaim | 95 | 51% | better MAE (6.2 vs 7.1) |
| failed_breakdown | 258 | 45% | |
| Mancini-level anchors | 140 | 47% | — |
| **LVN anchors** | 213 | **47%** | *identical* — prior-session LVNs are as good as Mancini levels for this purpose, and they exist every day |
| Full-RTH days | 217 | 45% | bigger excursions both ways |
| Late-day tape | 136 | 50% | tighter everything |

## What this does and does not say

- **Bullish-only:** supports-as-anchors means no bearish recognitions were
  graded. The b-day 32% is bullish confirms fighting a down tape, not evidence
  about shorting.
- **±5 symmetric is not the trade.** Flies and singles have asymmetric payoff;
  a 65%-win pocket with 9.4/4.5 excursion is far better than 65% suggests, and
  the ±5 grade understates fat-MFE confirms that take early heat.
- **Day-type cut is hindsight** until the developing-shape gate exists.
- LEG A (Steve grades confirms real/marginal/noise from the chair) is still
  open — these are mechanical grades only.

## Recommendations (in leverage order)

1. **Developing-day-type gate** on confirms (suppress/downgrade when the
   developing profile is b-shaped) — turns 47% raw into the 65% pocket
   without lookahead, if the developing classifier holds up.
2. **Keep the midday no-trade window** — now measured, not just doctrine.
3. **Prefer level_reclaim confirms late-day** — best MAE profile in our window.
4. **LVN anchors are first-class** — the anchor-availability problem for
   unlettered days is solved; wire prior-session LVNs into the shared anchor
   rule (`market/orderflow/anchors.py`).
5. Re-grade with an asymmetric target/stop matched to the fly entry (e.g.
   +8/−4) before drawing sizing conclusions.
