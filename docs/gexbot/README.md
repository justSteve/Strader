# GexBot — Reference Documentation

Documentation for GexBot's State subscription, organized into a deliberate
separation between immutable vendor truth and everything else.

## The architecture

This layout enforces an operational discipline: when we observe a
divergence between what GexBot's model predicts and what we measure in
the corpus, we want to know whether the gap is in *the model*, *our
interpretation of the model*, *the measurement*, or *the comparison
logic*. Mixing them in one place destroys that signal.

| Box | What lives here | Mutability |
|---|---|---|
| `canonical/` | Verbatim vendor-published documentation. The contract we measure against. | Immutable until vendor updates. Each change recorded in revision log. |
| `community/` | Practitioner / Discord / community methodology (e.g. `community/freddy_video.md`). Secondary sources interpreting the canonical. | Updated freely as new sources appear. |
| `transcripts/` | Primary-source recordings for any community content (e.g. video transcripts). Cited by `community/*.md` files. | Append-only — original recordings are evidence. |
| `gexbot.spec3.yaml` | OpenAPI spec (canonical, machine-readable). | Immutable until vendor updates. |

The *measured* side lives outside this directory:

| Box | Where | What's measured |
|---|---|---|
| Live data | `data/corpus/YYYY-MM-DD/gexbot.jsonl` | Cycle-by-cycle State responses, raw, append-only |
| Cross-stream | `data/corpus/YYYY-MM-DD/{schwab,databento_opra}.jsonl` | Schwab session data + OPRA tick tape, same date |

And the *comparison* between canonical and measured will land in:

| Box | Where (planned) | Purpose |
|---|---|---|
| Comparison checks | (TBD — likely `market/corpus/checks/`) | Pure functions that take a corpus row + a canonical assertion and emit pass/fail/divergence. The "did what canonical predicts actually happen" framework. |

## Why the separation matters

The canonical docs say things like: *"As price gravitates towards customer-long
options, holders are likely to liquidate, providing liquidity and
stifling movement."* That's a falsifiable prediction. The corpus records
what actually happened on each session. The comparison framework is the
code that asks: did customer-long-gamma strikes actually behave that way
on Tuesday? On Wednesday? Across 20 sessions? Where does the prediction
hold, and where does it break?

Without the separation, the "canonical text" gets paraphrased into
practitioner language, which gets paraphrased into Claude's
interpretation, which gets compared against vibe-based intuition about
the data. That's not measurable. With the separation, every claim has a
verifiable source and a measurable comparison.

## Current state

| File | Status |
|---|---|
| `canonical/README.md` | Layout + contract |
| `canonical/options_profile.md` | OP description, customer-long-vs-short bias logic, wall/accelerator behavior, volatility regime modulation |
| `canonical/gex_profile.md` | GEX Profile — orderflow-classification engine, high/low gamma nodes, full/latest/next variants |
| `canonical/dex_ladder.md` | DEX Ladder — delta exposure per strike, vol-regime modulation of DEX usefulness |
| `canonical/vanna_charm_ladder.md` | -Vanna / Charm Ladder (beta) — late-day dominance over gamma, polarity-flip dynamics |
| `canonical/convexity_ladder.md` | Convexity Ladder — vol-regime polarity table, 0DTE pinning mechanism |
| `canonical/metrics_math.md` | GEX/DEX/VEX/Charm formulas + 2 vendor-recommended teaching videos linked |
| `community/freddy_video.md` | Restructured 2026-05-22 to cite canonical as primary |
| `transcripts/2026-01-24_freddy_trading_with_gamma.{txt,json}` | Full 55-min auto-captioned transcript |
| `gexbot.spec3.yaml` | OpenAPI v2.2.0, pulled 2026-05-21 from nfa-llc/gexbot-openapi master |
| Comparison framework | Bead `st-cgb` (P2), deferred until corpus has ~5-10 days of data |
| Vendor video transcripts | Pending — `-RhSCoElB9Y` (Vanna and Charm Exposure), `zfkOCc2evEk` (Gamma and Vanna exposures). Steve to acquire transcripts next session. |
