# GEX Profile — Canonical

**Source:** <https://www.gexbot.com/documentation>, "state" section
**Captured:** 2026-05-20 from `documentation - gexbot.html` saved by Steve
**Status:** verbatim quotation. Do not paraphrase or edit; if vendor updates, replace the relevant block and note in revision log.

---

## GexBot State and the GEX Profile

> The gex profile takes the results of our orderflow-classification engine and isolates the greatest inflection points in the market. Here's how we do it:
>
> 1. The OP measures the net imbalance of transactions so far that day. What this means is that if one customer buys an option and another customer sells it, it won't show up on our chart. If a dealer buys an option, and then sells it, it also won't show up on our chart. If there's excess demand or excess supply for a contract, it will show up.
>
> 2. The typical assumption regarding options positioning is that dealers will delta hedge dynamically and that customers won't, which leads to a myopic focus on dealer positioning. But customers in aggregate will reposition themselves in line with their optimal incentives. So only thinking in terms of dealer positioning only gives you half of the truth.
>
> 3. Wherever there is a net imbalance, there is a seller on the other side (regardless of dealer/customer) who will be forced to adjust. If there is a net imbalance of puts equal to calls, then those sellers would get squeezed in opposite directions at the same time.
>
> 4. Gex profile therefore nets out imbalanced calls against imbalanced puts (regardless of dealer/customer) to locate areas where there is imbalanced exposure. We display call gex imbalance to the right and put gex imbalance to the left. This helps us quickly distinguish between **high gamma nodes (targets), low gamma nodes (transition areas), and call/put gamma regimes**.

## Versions and features

> We run two versions, both with the applicable features of gexbot classic (lookback dots, history slider, major levels):
>
> - **full** reflects classified orderflow on all expires within 90 days.
> - **latest** reflects classified orderflow in the nearest expiry.
> - **next** reflects classified orderflow in the following expiry.

## Customization

> gexbot state is highly customizable. Settings include: color settings for every element on the chart; line-type settings for every line on the chart (solid | simple-dashed | dashed | dotted); size settings for every dot on the chart; ability to enable/disable chart elements; price multiplier setting to convert between indexes/etfs.

## Historical data and alerts

> gexbot state includes historical data and alerts: load and review any day within the last 90 calendar days for any chart type and available ticker; alerts for spot price touching major call and major put; alerts for spot price touching major long and major short gamma (see convexity ladder); running record of your triggered alerts.

---

## Observations derivable from this passage

These are *implications* of the canonical text, included to make
operational handles explicit. They are not canonical — they are targets
for the measurement framework to validate against corpus data.

1. **Classification reads net imbalance, not raw flow.** Symmetric two-side trades zero out. What remains is excess demand or supply per strike — that's the entire signal.

2. **High vs low vs regime — three reads from the same chart:**
   - **High gamma node** at a strike → target (price drawn there)
   - **Low gamma node** at a strike → transition area (price passes through)
   - **Call/put regime** across the strike range → directional bias of the day

3. **"Full" vs "latest" vs "next" maps to API category enum:** `gex_full` / `gex_zero` / `gex_one` per the OpenAPI spec at `../gexbot.spec3.yaml`. For 0DTE late-day work, `gex_zero` is the relevant pull.

4. **Net imbalance principle matters for measurement framework.** When comparing GexBot's `major_positive` and `major_negative` against actual price behavior, the prediction is about *net imbalance* concentrations, not gross flow. Falsification needs to be measured against the right metric.

## Revision log

- 2026-05-22: Initial canonical capture from `documentation - gexbot.html` saved 2026-05-20. Promoted by Steve direction same day.
