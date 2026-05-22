# GexBot — Canonical Documentation

This directory holds **verbatim** vendor-published content from GexBot's
documentation pages. The contract:

- Content is treated as **immutable** until proven wrong by the vendor or by sustained empirical contradiction.
- Each file declares its source URL and the date the content was captured.
- No editorial interpretation, no compression, no paraphrasing — what's quoted is what GexBot publishes.
- Practitioner interpretations, community methodology, and our own derivations live elsewhere (`../community/`, `../../../market/corpus/`).

The separation enforces a discipline: when our measured behavior in the
corpus disagrees with what's in this directory, we have a real
divergence worth investigating — not a question of "did Claude
paraphrase the docs accurately." The canonical text is the contract.

When GexBot updates their docs, we update the corresponding file here and
note the change in the file's revision log. The git history is the audit
trail.

## Layout

| File | Source page | Covers |
|---|---|---|
| `options_profile.md` | <https://www.gexbot.com/documentation> (state section) | Options Profile, customer-long-vs-short bias logic, wall/accelerator behavior, **volatility regime modulation** |
| (future) `state_indicators.md` | same | GEX Profile, DEX Ladder, Convexity Ladder, -Vanna/Charm Ladders |
| (future) `metrics_math.md` | <https://www.gexbot.com/metrics> | GEX, DEX, VEX, Charm formulas (the math behind the indicators) |
| (future) `api_reference.md` | <https://www.gexbot.com/apidocs> + `../gexbot.spec3.yaml` | Endpoint behaviors, rate limits, auth |

Files are added as the corresponding GexBot content is ingested. Empty
slots above are planned, not promised.
