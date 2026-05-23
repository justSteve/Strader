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
| `options_profile.md` | <https://www.gexbot.com/documentation> (state section) | Options Profile (OP), customer-long-vs-short bias logic, wall/accelerator behavior, **volatility regime modulation** |
| `gex_profile.md` | same | GEX Profile — orderflow-classification model, high/low gamma nodes, full/latest/next variants |
| `dex_ladder.md` | same | DEX Ladder — delta exposure per strike, the "options order book" framing, vol-regime modulation of DEX usefulness |
| `vanna_charm_ladder.md` | same | -Vanna / Charm Ladder — beta-tagged, late-day dominance over gamma, polarity-flip behavior across spot |
| `convexity_ladder.md` | same | Convexity Ladder — risk-not-direction read, vol-regime polarity table (positive stalls in falling vol, negative stalls in rising vol), 0DTE pinning mechanism |
| `metrics_math.md` | <https://www.gexbot.com/metrics> | GEX, DEX, VEX, Charm formulas (the math behind the indicators); two vendor-recommended teaching videos linked at the end |
| `gamma_vanna_video.md` | <https://www.youtube.com/watch?v=zfkOCc2evEk> | Vendor-recommended video #1 — gamma exposure mechanics, the implied order book, why net gamma rarely goes negative, the vanna bridge |
| `vanna_charm_video.md` | <https://www.youtube.com/watch?v=-RhSCoElB9Y> | Vendor-recommended video #2 — delta-as-ITM-probability reframing, four worked vanna cases, charm as time-substitution for vanna, the combined-mechanism rally/pin |
| `principal_discord.md` | GexBot Discord (jass, John Kirby) | Principal-sourced Discord Q&A. Treated as first-party doctrine — supersedes community interpretations. Parallel to `../community/discord_quotes.md` but for staff voices. |
| (future) `api_reference.md` | <https://www.gexbot.com/apidocs> + `../gexbot.spec3.yaml` | Endpoint behaviors, rate limits, auth (probably redundant with the OpenAPI spec; defer until clear value) |

Files are added as the corresponding GexBot content is ingested. Empty
slots above are planned, not promised.
