# Plan — Richer Mancini Extraction

**Bead:** st-9r51 · **Written:** 2026-08-20 · **Status:** plan, not a build ·
**Reads:** `runbook/mancini/extraction-contract.md` (the starting point, per the bead)

---

## The gap in one line

The **numbers** are coded and reliable — `listlevels.py` scrapes them
deterministically, and without `--extraction-json` the run publishes those alone.
What is missing is everything Mancini says *about* the numbers: which level he'd
actually trade versus merely name, what he expects at it, the conditional
structure, and his confidence language.

The 2026-08-11 case is the whole argument: the useful read of Steve's fly was
that its centre sat on *"the first support down, weak and shaky, I won't touch
it"*. **That phrase is in the letter and in no structured field.**

## What the corpus says — measured, not assumed

The bead notes "his letter has recurring phrasing" and asks which parts can be
deterministic. Measured over **330 clean letters** (`data/mancini-letters-clean/`):

**Section anchors are near-universal — deterministic splitting is safe.**

| anchor | letters | % |
|---|---|---|
| `Bull case` | 316/330 | 95.8% |
| `Bear case` | 310/330 | 93.9% |
| `In summary` | 310/330 | 93.9% |
| `Supports are:` | 310/330 | 93.9% |
| `Resistances are:` | 308/330 | 93.3% |

**Directional conditionals are near-universal too.**

| pattern | letters | % |
|---|---|---|
| `above <price>` | 295/330 | 89.4% |
| `below <price>` | 293/330 | 88.8% |
| `Failed Breakdown` | 316/330 | 95.8% |
| `actionable` | 315/330 | 95.5% |
| `target(s) <price>` | 195/330 | 59.1% |
| `defend <price>` | 147/330 | 44.5% |
| any conditional at all | 316/330 | 95.8% |

**But the judgement colour is long-tail, and this is the finding that shapes the
split.** Counting only sentences that contain a price:

| phrase | letters | % |
|---|---|---|
| recover | 316 | 95.8% |
| flush | 312 | 94.5% |
| first support | 260 | 78.8% |
| backtest | 236 | 71.5% |
| shelf of lows | 234 | 70.9% |
| magnet | 170 | 51.5% |
| defended | 69 | 20.9% |
| **weak** | **23** | **7.0%** |
| **shaky** | **4** | **1.2%** |
| **heavily used** | **3** | **0.9%** |

> **The recurring vocabulary is Mancini's *mechanism* language — flush, recover,
> backtest, shelf, magnet — at 50–96%. The vocabulary that made the 08-11 example
> worth having — *weak*, *shaky*, *heavily used* — appears in 1–7% of letters and
> is phrased differently each time.**

This inverts the natural assumption. One might expect the colour to be formulaic
and the structure to be free-form; it is the reverse. **A scrape can carry the
mechanism reliably and will never carry the conviction.**

## The two tiers

### Tier 1 — deterministic, no model, extends `listlevels.py`

Reachable on its own, with the corpus percentages above as the confidence:

1. **Section attribution.** Split on the five anchors; tag every level and
   sentence with the section it came from (`bull_case` / `bear_case` /
   `in_summary` / `supports_list` / `resistances_list`). Feeds `commentary.tags`
   directly.
2. **Mechanism tags per level.** A closed vocabulary — `flush`, `recover`,
   `backtest`, `shelf_of_lows`, `shelf_of_highs`, `magnet`, `failed_breakdown`,
   `actionable`, `first_support`, `first_resistance` — matched in the sentence
   containing the price. These are Mancini's method words, they recur, and they
   are exactly what makes an alert legible.
3. **Conditional skeletons.** `above N` / `below N` / `loses N` / `reclaims N` /
   `defends N` / `targets N` → `trigger.type` (`price_cross` or `price_zone`) plus
   `anchor_prices`. The contract's enum already fits this with no change.
4. **`source_quote` for every one of the above** — the minimal span, per the
   existing accuracy rule.

**What Tier 1 alone reaches:** every level keeps its numbers and gains its
section, its mechanism tags and its machine-readable trigger. An alert can then
say *"2 points under 7745 — bear-case Failed Breakdown level, flush-and-recover"*
without a model anywhere in the path.

**What Tier 1 can never reach:** *"weak and shaky, I won't touch it."* Not a
tuning problem — the phrasing genuinely varies.

### Tier 2 — model-required

1. **Conviction / tradeability.** Which levels Mancini *wants traded* versus
   merely names. Nothing lexical marks this; it is the point of the bead.
2. **The long-tail callout phrase** — the `label` colour, per the contract's
   "put Mancini's own words in `label`" rule.
3. **`session_bias`** — a prose summary, already model-shaped.
4. **The runners/position exclusion.** The contract's narrow carve-out (drop *his
   positions*, keep the level's character) is a judgement a regex will get wrong
   in exactly the way the contract warns about: an earlier reading "collapsed
   every callout to major/minor and stripped the plan of its colour."

## Failure behaviour at 08:15

**Unchanged from today, and that is deliberate.** The parse runs fifteen minutes
before the open with no second chance before the bell.

- **Tier 1 is part of the deterministic path.** It runs in-process, adds no
  network call, and cannot be slow. If a section anchor is missing (4–7% of
  letters), the affected levels simply carry no section tag — they do not fail.
- **Tier 2 is strictly additive.** If it fails, is slow, or is skipped, the run
  publishes Tier 1 exactly as it publishes deterministic levels today: alert,
  keep last-good, exit non-zero rather than publish suspect levels.
- **The existing `model` stamp already distinguishes the routes**
  (`in-session:<label>` versus `deterministic-lists`), so a Tier-1-only day is
  visible in the store rather than silently thinner. Add one value —
  `deterministic-enriched` — so the three routes are distinguishable.

**No design here lets a Tier 2 failure cost the session its levels.**

## Cost — and this needs Steve's ruling

**Tier 1 costs nothing.** No API, no standing spend, no model. It is a harness
change and lands under the harness-first directive without a decision.

**Tier 2 is where the ruling sits.** Parsing is prompt-driven in-session today
and deliberately so — no `llm.py` runs, no Console top-up. Two routes:

| route | cost | reliability at 08:15 |
|---|---|---|
| **(a) Keep in-session** (status quo) | none | depends on a session being open at 08:15 |
| **(b) Automated API call** | standing spend, per letter, every trading day | independent of a session |

**Recommendation: (a).** Tier 1 closes most of the alert-legibility gap for free,
and the in-session parse already produces Tier 2 fields on the days Steve runs
`/mancini-parse`. That makes (b) an optimisation for unattended days rather than
a requirement — worth revisiting only if Tier 1 ships and the remaining gap still
bites. **This is a proposal for Steve to rule on, not an implementation detail.**

## How it reaches the sentinel

The level list is the hand-off. `data/level_state/current.json` records already
carry `price`, `kind`, `major`, `label`, `source_quote`, plus live state
(`state`, `n_touches`, `n_defenses`, `break_time`, `reclaim_time`, `extreme`).

**Four fields ride along with each level, all Tier 1:**

```jsonc
"section":      "bear_case",              // which paragraph it came from
"mechanism":    ["failed_breakdown", "flush_and_recover"],
"triggers":     [{"type": "price_cross", "direction": "below",
                  "anchor_prices": [7745], "condition_text": "..."}],
"tradeable":    null                      // Tier 2 fills; null means unknown, never false
```

`tradeable` defaults to `null` rather than `false` on purpose — a Tier-1-only day
must not tell the sentinel that Mancini declined a level he never judged.

This turns the bead's weak alert into its strong one **without the sentinel
learning anything about how the parse ran.**

## Sizing

**Tier 1 is one session.** It is a scrape extension over `listlevels.py` plus
four additive schema fields and their validation, with 330 letters on disk as the
test corpus and the per-pattern percentages above as the regression targets.

**Tier 2 is not a build at all** until the cost question is ruled — it is the
existing in-session prompt plus two contract fields.

**Staging: Tier 1 first, alone.** It is free, it is testable against the whole
corpus, and it is what the sentinel needs most.

## Open questions for Steve

1. **The API-spend ruling** above — (a) keep in-session, or (b) automate. One
   word; my recommendation is (a).
2. **`mechanism` vocabulary is closed.** I have proposed ten tags from the corpus
   frequencies. Adding one later is cheap; the list should be reviewed once
   rather than grown ad hoc.
