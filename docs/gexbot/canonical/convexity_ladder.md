# Convexity Ladder — Canonical

**Source:** <https://www.gexbot.com/documentation>, "state" section
**Captured:** 2026-05-20 from `documentation - gexbot.html` saved by Steve
**Status:** verbatim quotation. Do not paraphrase or edit; if vendor updates, replace the relevant block and note in revision log.

---

## State Convexity Ladder

> The convexity ladder takes the net imbalance of transactions so far that day and displays the net gamma exposure of those positions. Long calls and long puts represent long customer gex, while short calls and short puts represent short customer gex.
>
> We use convexity rather than the simpler "gex ladder" because we want to convey the chart's significance in a more visceral way:
>
> - **Positive convexity:** Customers own convexity, favoring moves that exceed expectations. Ideally, they want price traveling as far away from their positive strikes as possible.
> - **Negative convexity:** Customers are short convexity, favoring moves that underperform expectations. Ideally, they favor price approaching and resting at their negative strikes.

## Risk reading vs direction reading

> Reading the convexity ladder is less about discerning direction, and more about measuring risk. For example, our favorite SPY setup (infrequent, but explosive) occurs when a single strike of negative convexity dwarfs all others as spot hovers just above. Being short convexity at the wrong time in a crowded place can cause cascading panic, if given a gentle shove. Perhaps no shove occurs, but one can be ready in case it does.

## Using the Convexity Ladder as a Map

> When we use the convexity ladder as our map, we can gain an understanding of the terrain — distinguish between mountains and grasslands:
>
> **In a falling volatility environment (most common):**
> - Positive convexity stalls price
> - We soar right through negative convexity
>
> **With rising volatility:**
> - We glide through positive convexity
> - We stall at negative convexity
>
> In either case, transition points between positive and negative convexity act as pivots: They are where incentives change and traders reshuffle.

## Convexity Ladder and the Volatility Environment

> An overview of the convexity ladder as a whole, as well as its distribution, can give us an idea of our volatility environment:
>
> - **Significant and well-distributed negative convexity:** We are trading in liquid markets as traders are happy to sell options. (Concentrated negative convexity is a clear exception.)
> - **Significant and well-distributed positive convexity:** Indicates an elevated and well-informed expectation of volatility. We typically see this prior to days with event-driven volatility.

## Note on Pinning

> As we head into close, **0DTE negative convexity (dealer long strikes) act as magnets for price due to -vanna and charm effects.** More on this later.

---

## Observations derivable from this passage

These are *implications* of the canonical text. Not canonical — targets
for the measurement framework.

1. **Sign convention for "customer convexity":**
   - Positive customer convexity = customer long calls/puts = customer owns optionality
   - Negative customer convexity = customer short calls/puts = customer is short optionality
   The dealer side is the inverse.

2. **Vol-regime modulation of price behavior (this is the key operational read):**

   | Vol regime | Positive convexity | Negative convexity |
   |---|---|---|
   | **Falling** (most common) | Stalls price (wall) | Price soars through (passes) |
   | **Rising** | Price glides through (passes) | Stalls price (wall) |

   This is the *concrete polarity flip* version of the rising-vol modulation referenced in `options_profile.md`. Same model, sharpened to convexity terms.

3. **Pinning is explicit at close:** 0DTE negative convexity (= dealer long strikes) act as magnets due to vanna/charm. This is the canonical statement of the pinning mechanism that underlies the late-day fly thesis.

4. **Cross-validation handle:** `major_short_gamma` (from `gex_zero` response) and "negative convexity strikes" (from convexity ladder) should reference the same underlying positions. They are different aggregations of the same orderflow-classified data.

5. **Distribution shape matters, not just peaks:**
   - Well-distributed *negative* convexity → liquid, traders selling options (everyday market)
   - Well-distributed *positive* convexity → traders pricing event vol (pre-news, pre-earnings, etc.)
   This is a regime indicator independent of price level — useful for tagging session character in the corpus.

6. **Transition points = pivots** (independent of vol regime). Where convexity flips sign across strikes, incentives change. These should align with the "transition points" referenced in `dex_ladder.md`.

7. **Convexity ladder ≠ GEX profile — do not confuse the axes.** This ladder nets **long vs short** contracts (regardless of call/put), with **cyan = long gamma, purple = short gamma**. The separate GEX profile (green/red) nets **calls vs puts** (regardless of long/short). Per Jasper's Discord Q&A:
   - **call/put gex** → measure of directional (up/down) convexity
   - **long/short gamma** → measure of momentum/reversion (continuation or fade)

   A trade decision typically wants both: GEX profile picks the *level*; this ladder predicts the *behavior at that level* (continuation vs reversion). See [`principal_discord.md`](principal_discord.md) for the full Q&A series, including the 2025-02-21 closing exchange where Jasper establishes the canonical operational rule.

8. **The canonical operational rule (Jasper, 2025-02-21):** customer-perspective always.

   > **Pivot at customer long gamma (cyan). Move through customer short gamma (purple). That's all you really need.**

   "Pivot" means price reverses at the level (cyan zones stall and revert). "Move through" means price traverses without stalling (purple zones are transit areas). This compresses the vol-regime modulation in observation 2 and the transition-points-as-pivots in observation 6 into a single default heuristic. The vol-regime polarity flip remains the override: in rising vol, the polarity inverts.

9. **NEW from Q&A: negative gamma line aligns with the volume-profile POC.** GexBot staff stated (2025-02 exchange) that the negative gamma line on the convexity ladder falls at the Point of Control — the volume-profile price with the highest traded volume, where indecisive trading concentrates. Worth investigating: if this holds across sessions, the gamma ladder gives us a derivable POC estimate without needing a separate volume profile pull.

10. **Convexity ↔ gamma label equivalence (John Kirby, 2025-02-21 8:04 AM):** The vendor docs' "positive/negative convexity" terms and the UI's "long/short gamma" labels are the *same data with different vocabulary*.

    | Vendor docs term | UI gamma-ladder label | Color |
    |---|---|---|
    | Positive convexity | Long gamma | Cyan |
    | Negative convexity | Short gamma | Purple |

    "Positive convexity" in this file's vendor quotation is identical to "long gamma" in the operational docs. No conversion needed. See [`principal_discord.md`](principal_discord.md) entry 6 for the verbatim statement.

## Revision log

- 2026-05-22: Initial canonical capture from `documentation - gexbot.html` saved 2026-05-20.
- 2026-05-22: Added observation 7 (axis disambiguation from GEX profile) sourced from Jasper Discord Q&A; archived in `principal_discord.md`.
