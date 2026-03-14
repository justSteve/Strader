# Rule: Price Action Interpretation Protocol

When Steve shares /ES charts or asks for PA interpretation, you are working with three LuxAlgo indicators simultaneously. Your job is to read all three as an ensemble, not individually.

## Prerequisites — Settings Audit Must Complete First

**Before any live PA interpretation session, the settings audit must be complete.** See `indicators/settings-audit-guide.md` for the full walkthrough.

The audit has four phases:
1. **Capture**: Steve screenshots each indicator's settings panels
2. **Review**: Walk through every setting — what it does, current vs. default, implications on 1-min /ES, trade-offs
3. **Cross-indicator coherence**: Are the three indicators configured to work together or fighting each other?
4. **Baseline**: Document the agreed configuration. All future tuning references this baseline.

If the audit has not been completed, do not proceed to live interpretation. Instead, initiate the audit workflow.

The audit baseline is stored in `indicators/settings-baseline.md` once established. If that file does not exist, the audit is incomplete.

## Reference Documents

Full indicator documentation with every setting, signal type, and interpretation rule:
- `indicators/luxalgo-oscillator-matrix.md` — Oscillator Matrix (below-chart: HyperWave, Money Flow, Reversals, Confluence)
- `indicators/luxalgo-signals-overlays.md` — Signals & Overlays (on-chart: signals, overlays, TP/SL)
- `indicators/luxalgo-price-action-concepts.md` — Price Action Concepts (on-chart: structure, order blocks, liquidity, FVGs)
- `indicators/settings-audit-guide.md` — Full settings audit walkthrough with per-setting analysis for 1-min /ES

Read these files when you need to reference specific settings or interpretation rules during a session.

## Screenshot Interpretation Sequence

When Steve shares a chart screenshot:

1. **Structure first**: What is the current market structure? Identify the most recent BOS or CHoCH on both internal and swing timeframes. Is the trend continuing or reversing?

2. **Key levels**: Where are the active order blocks? Any unmitigated FVGs? Where are premium/discount zones relative to current price?

3. **Oscillator state**: What is HyperWave doing relative to its signal? Is Money Flow above/below thresholds? Any overflow? What does confluence read?

4. **Signal assessment**: Are there active Signals & Overlays signals? What mode and rating? Do overlay trails (Smart Trail, Trend Catcher) agree with structure?

5. **Confluence synthesis**: Where do the three indicators agree? Where do they diverge? State the confluence level plainly.

## Confluence Framework

**High confidence (act)**: Market structure + oscillator + signal overlay all agree
- Example: Bullish CHoCH + HyperWave oversold turning point with strong confluence + bullish confirmation signal rating 3-4 near a bullish order block in discount zone

**Medium confidence (prepare)**: Two of three agree, one neutral or lagging
- Example: Bullish BOS + HyperWave rising but no turning point yet + Smart Trail bullish

**Low confidence (wait)**: Only one indicator signaling, others mixed or opposed
- Example: Bullish confirmation signal but HyperWave overbought, bearish CHoCH forming on internal structure

**Conflict (stand aside)**: Indicators actively disagree
- Example: Bullish signal overlay but bearish swing CHoCH with Money Flow below lower threshold

## Output Format

For PA interpretation responses, use this structure:

```
STRUCTURE: [Internal: X | Swing: Y]
KEY LEVELS: [OBs, FVGs, zones relative to price]
OSCILLATOR: [HyperWave X/100 | MF: above/below/between | Confluence: 0/1/2]
SIGNALS: [Active signal type + rating if ML enabled]
CONFLUENCE: [High/Medium/Low/Conflict] — [1-sentence synthesis]
```

Expand only when Steve asks for detail. Default to table-dense, minimal prose.

## Tuning Sessions

When Steve wants to adjust indicator settings:
1. Read the relevant indicator doc for current defaults and options
2. Propose specific setting changes with rationale tied to what Steve is seeing
3. After Steve applies changes and shares a new screenshot, compare before/after
4. Document effective settings changes for future sessions

## What You Do NOT Do

- Do not predict price direction as financial advice
- Do not recommend specific trades
- Do interpret what the indicators are saying and assess their agreement level
- Present indicator readings as data, not recommendations
