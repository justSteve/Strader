# DEX Ladder — Canonical

**Source:** <https://www.gexbot.com/documentation>, "state" section
**Captured:** 2026-05-20 from `documentation - gexbot.html` saved by Steve
**Status:** verbatim quotation. Do not paraphrase or edit; if vendor updates, replace the relevant block and note in revision log.

---

## State DEX Ladder

> Options profile can be a lot of information to take in at once. The dex ladder takes the net imbalance of transactions so far that day and displays the delta exposure at each strike. Customer long calls and short puts have positive delta, while customer short calls and long puts have negative delta. Instead of having two bars per strike, dex allows us to have one. It shows us where participants are short, where they are long, and by how much. We can anticipate which levels will be heavily defended, and which levels will be decisive once overcome. Transition points between heavy short interest and traders attempting longs, for instance, signal targets and possible reversion zones.

## DEX as options order book

> The dex ladder is the options version of the current order book. Heavy short interest coming in above spot is a warning sign (much like a passive limit seller coming in above spot), just as heavy long interest (passive limit buyer) coming in below can be supportive. On underlyings, like SPY, for which options are most often traded directionally, a glance at the dex ladder can also be a quick way of developing a bias: How aggressively are traders positioned today?

## Volatility regime modulation

> One additional advantage is worth noting: In higher volatility environments, the gamma curve flattens out, **strengthening the relationship between dex and price movement**. More simply, the delta of a transaction becomes increasingly relevant as liquidity dries up. Accordingly, we rely more on dex as things heat up.

---

## Observations derivable from this passage

1. **Delta sign convention** (canonical):
   - Customer long calls, customer short puts → positive delta
   - Customer short calls, customer long puts → negative delta

2. **One bar per strike** — DEX collapses the OP's call+put two-bar view into a single signed delta exposure, easier to read at a glance.

3. **Operational reads:**
   - Heavy *short* interest above spot → warning (resistance / passive seller analog)
   - Heavy *long* interest below spot → supportive (passive buyer analog)
   - **Transition points between heavy short and heavy long** → targets / reversion zones

4. **DEX is volatility-regime sensitive in the opposite direction from gamma:** in *high vol* environments, dex becomes *more* informative (gamma curve flattens, delta-of-transactions dominates). For our framework: when ATM IV is elevated, weight DEX reads higher than GEX reads.

5. **SPX vs SPY contrast (implied):** the passage references SPY as a case where options are traded directionally, making DEX a good bias proxy. SPX (institutional) flow may carry less directional bias and more hedging/structural positioning — DEX read should be cross-checked against GEX read on SPX rather than taken at face value.

## Revision log

- 2026-05-22: Initial canonical capture from `documentation - gexbot.html` saved 2026-05-20.
