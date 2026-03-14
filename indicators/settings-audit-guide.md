# LuxAlgo Settings Audit Guide — 1-Min /ES

This guide drives the preparatory stage before live PA sessions. Steve shares screenshots of his current settings panels. Strader walks through every setting, explains what it's doing at the current value, identifies defaults vs. intentional choices, and surfaces improvement opportunities.

**This stage must complete before any live interpretation session.**

---

## How to Run the Audit

### Step 1: Capture Current State
Steve screenshots each indicator's settings panel in TradingView:
- Oscillator Matrix: Full settings panel (scroll to capture all sections)
- Signals & Overlays: Full settings panel
- Price Action Concepts: Full settings panel

### Step 2: Setting-by-Setting Review
For each setting, Strader covers:
1. **What it controls** — the mechanism, not just the label
2. **Current value vs. default** — is this intentional or untouched?
3. **What this value means on 1-min /ES** — specifically, how does this timeframe change the calculus?
4. **Trade-off spectrum** — what you gain and lose by moving the value up or down
5. **Recommendation** — keep, adjust, or experiment — with rationale

### Step 3: Cross-Indicator Coherence
After individual review, assess whether the three indicators are configured to work together:
- Are sensitivities aligned or fighting each other?
- Is one indicator set for swing while another is set for scalp?
- Are features duplicated across indicators (redundant noise)?
- Are complementary features left off that would fill gaps?

### Step 4: Baseline Document
Capture the agreed-upon configuration as a baseline. Future tuning sessions reference this.

---

## Oscillator Matrix — Settings Audit

### HyperWave Section

#### Show HyperWave (toggle)
**Mechanism**: Master on/off for the primary oscillator line.
**Default**: true
**1-min /ES note**: Should always be on. This is the core trend/reversal read.
**If off**: You lose the primary oscillator, turning points, and divergence detection. No reason to disable.

#### HyperWave Length (numerical)
**Mechanism**: Controls how many bars the oscillator considers. Directly affects responsiveness vs. smoothness.
**Default**: 7
**Trade-off spectrum**:
| Value | Behavior on 1-min /ES |
|-------|----------------------|
| 3-5 | Very reactive. Catches micro-moves. More noise, more false turning points. Suited for pure scalping (30-second holds) |
| 6-8 | Balanced for 1-min. Captures 3-8 minute price swings. Default (7) is a reasonable starting point |
| 9-12 | Smoother. Misses short impulses but cleaner trend reads. Better if you're holding 10+ minutes |
| 13+ | On 1-min chart, this starts acting like a 5-min oscillator. Significant lag for entry timing |

**Key question**: How long are your typical /ES trades? If 3-10 minutes, keep 5-8. If 10-20 minutes, go 8-12.

#### Signal (dropdown: SMA or Trailing Stop)
**Mechanism**: The algorithm used to generate the signal line that HyperWave crosses to produce turning points.
**Default**: SMA
**SMA**: Simple moving average of HyperWave. More responsive to price changes. Produces more turning points. Better at lower HyperWave lengths.
**Trailing Stop (TS)**: Uses trailing stop methodology. Less sensitive to HyperWave noise. Produces fewer, higher-quality turning points. Better when HyperWave Length is elevated (10+).
**1-min /ES note**: If HyperWave Length is 5-8, SMA is appropriate. If you push length higher (10+), switch to TS to avoid signal line whipsawing.

#### Signal Length (numerical)
**Mechanism**: Period applied to whichever signal algorithm is selected. Controls signal line smoothness.
**Default**: 3
**Trade-off**: Lower = signal line hugs HyperWave closely = more turning points = more noise. Higher = signal line smooths out = fewer turning points = more lag.
**1-min /ES note**: At default length 7 with SMA, signal length 3 is responsive. If you find too many green/red dots firing (whipsaw), try 4-5 before changing HyperWave Length.

#### Colors (numerical)
**Mechanism**: Transparency of the filled area between HyperWave and signal line. Purely visual.
**Default**: 80
**Note**: No analytical impact. Adjust for chart readability.

### Divergence Section

#### Divergence Sensitivity % (numerical)
**Mechanism**: Controls what qualifies as a divergence. Lower % = longer-term divergences only (requires larger price/oscillator disagreement). Higher % = shorter-term divergences (catches smaller disagreements).
**Default**: 10
**Trade-off**:
| Value | Behavior on 1-min /ES |
|-------|----------------------|
| 1-5 | Only catches major divergences spanning 20+ bars. Rare but high significance |
| 6-10 | Moderate. Catches divergences over 5-20 bars. Default (10) is a reasonable filter |
| 11-20 | More sensitive. Catches 3-10 bar divergences. More signals, some will be noise |
| 21+ | Very sensitive. Will fire frequently on 1-min /ES. Most signals won't lead to meaningful moves |

**1-min /ES note**: /ES moves fast. Divergences that develop over 5-15 bars (5-15 minutes) are the sweet spot. Default 10 is a reasonable starting point. If you're seeing divergences that resolve without meaningful price reaction, lower the value.

#### Show Divergences / Show Divergences On Chart (toggles)
**Mechanism**: Where divergence lines appear — oscillator pane only, or also on the price chart.
**Default**: Both true
**Note**: Chart divergence lines appear retrospectively (not at the moment of detection) and max out at 500 lines. The oscillator pane version is real-time. If chart gets cluttered, disable chart display and read divergences from the oscillator pane.

### Smart Money Flow Section

#### Money Flow (numerical)
**Mechanism**: Oscillator length for the money flow component. Controls what timeframe of participant activity it captures.
**Default**: 35
**Trade-off**:
| Value | Behavior on 1-min /ES |
|-------|----------------------|
| 15-25 | Short-term participant flow. Reactive but noisy. Catches 15-25 minute activity cycles |
| 26-40 | Medium-term. Default (35) captures roughly 30-40 minute activity patterns. Good for session-level trends |
| 41-60 | Longer-term. Captures 1-2 hour participant patterns. Less useful for scalping, good for trend bias |

**1-min /ES note**: Money Flow is designed to be longer-duration than HyperWave. The default 35 gives you a different timescale view — this is intentional. Don't tune it to match HyperWave's speed; the value is in the contrast.

#### Smooth (numerical)
**Mechanism**: Post-processing smoothing applied to Money Flow output. Reduces visual noise.
**Default**: 6
**Trade-off**: Higher = smoother line, easier to read trend but slower to react. Lower = more jagged but faster to show change.
**1-min /ES note**: Default 6 is reasonable. If Money Flow line is hard to read, increase to 8-10. Don't go below 4 on 1-min — too noisy.

### Reversal Section

#### Reversal Factor (dropdown: 1-10)
**Mechanism**: Sensitivity of the reversal detection algorithm. Higher = fewer detections (more selective).
**Default**: 5
**Trade-off**:
| Value | Behavior on 1-min /ES |
|-------|----------------------|
| 1-3 | Fires frequently. Many minor/major reversals. On 1-min /ES, expect a signal every few minutes. Most will be noise |
| 4-6 | Moderate selectivity. Default (5) is middle ground. Expect clusters around actual turning points with some false positives |
| 7-8 | Selective. Fewer signals, higher quality. May miss fast reversals |
| 9-10 | Very selective. Only major structural turns. Significant lag |

**1-min /ES note**: Start at 5. If you're seeing too many reversal signals that don't lead to meaningful moves, increase to 6-7. The minor (-) vs major (+) distinction already provides a quality filter — focus on major reversals for entries.

### Confluence Section

#### Upper/Lower Confluence (toggles)
**Mechanism**: Shows/hides the zones above 100 and below 0 that measure HyperWave + Money Flow agreement.
**Default**: Both true
**Note**: Always keep on. This is the core cross-component read. No reason to disable.

#### Show Confluence Meter (toggle)
**Mechanism**: Quantitative gauge tracking alignment across ALL oscillator components (HyperWave, Money Flow, overflow, divergences).
**Default**: false
**1-min /ES note**: **Turn this ON.** This is the single most useful confluence read in the Oscillator Matrix. It synthesizes everything into one number. The fact that it defaults to off is a missed opportunity in the default config.

#### Meter Width (numerical)
**Mechanism**: Visual thickness of the confluence meter line.
**Default**: 3
**Note**: Purely visual. Adjust for readability.

### Custom Alert Creator
Audit these only after all base settings are dialed in. Alert logic builds on top of indicator behavior — premature to configure until you trust the underlying signals.

### Calculated Bars
**Default**: 10000
**Note**: Number of historical bars processed. Lower = faster chart loading. On 1-min /ES, 10000 bars is ~16.7 trading days. Adequate unless you need deeper history.

---

## Signals & Overlays — Settings Audit

### Signal Configuration

#### Signal Mode (dropdown)
**Mechanism**: Selects the signal generation algorithm.
**Default**: Confirmation + Exits
**Options explained**:
- **Confirmation + Exits**: Trend-following. Signals fire during retracements within a trend. Lower risk entries but inherent lag. Strong (+) signals align with estimated trend.
- **Contrarian + Exits**: Reversal-seeking. Signals fire against the current trend. Faster entries but larger adverse excursions. Strong (+) fires at extreme overbought/oversold.
- **None**: Disables signal generation entirely.

**1-min /ES note**: Confirmation is the safer starting mode for /ES. Contrarian is useful but demands more experience reading when the indicator is right vs. early. Start with Confirmation; add Contrarian to a second instance of the indicator later if you want both views.

**Critical caveat**: Signals confirm at NEXT candle open. The signal you see on the current candle may repaint. Never act on an unconfirmed signal.

#### ML Signal Classifier (toggle + filter)
**Mechanism**: Rates each signal 1-4 using an adaptive threshold classifier.
**Default**: Off, filter "1234"
**Ratings in Confirmation mode**:
- 1-2: Potential reversals or retracements (trend may be weakening)
- 3-4: Trend continuation (higher confidence the signal aligns with trend)

**1-min /ES note**: **Turn ON.** Then observe for several sessions before filtering. Once you see the pattern, filter to "34" to show only high-confidence signals. This dramatically reduces noise.

#### Signals Sensitivity (numerical)
**Mechanism**: Primary reactiveness control. Affects both Confirmation and Contrarian signals.
**Default**: 12
**Trade-off**:
| Value | Behavior on 1-min /ES |
|-------|----------------------|
| 5-8 | Very reactive. Catches short impulses (2-5 bars). Many signals, many false |
| 9-12 | Moderate. Default (12) captures 5-15 bar price movements |
| 13-18 | Smoother. Targets 15-30 bar movements. Fewer signals, more lag |
| 19-25 | On 1-min, this is swing-trading territory. Significant entry delay |

**Key question**: Same as HyperWave Length — how long are your trades? Sensitivity and HyperWave Length should target the same timescale.

#### Autopilot Sensitivity (dropdown)
**Mechanism**: Dynamic sensitivity adjustment. Overrides manual Sensitivity value.
**Default**: Off
**Options**: Off, Short-Term, Medium-Term, Long-Term
**1-min /ES note**: Short-Term Autopilot lets the indicator adapt to /ES volatility changes throughout the session. Useful if you don't want to manually adjust sensitivity during RTH. Try it — if signals feel wrong, go back to manual.

### Overlay Settings

#### Smart Trail (toggle + period 1-5)
**Mechanism**: Adaptive trailing stop on chart. Blue = support, red = resistance.
**Default**: ON, period 3
**Trade-off**: Period 1-2 = tight, hugs price, flips frequently. Period 3-4 = moderate. Period 5 = wide, fewer flips, may be too slow for 1-min.
**1-min /ES note**: Period 2-3 for 1-min. If the trail is flipping bullish/bearish every few candles, it's too tight — go to 3. If it never flips during 10-15 bar trends, it's too loose — go to 2.

#### Trend Tracer (toggle + period 1-5)
**Mechanism**: Underlying trend direction estimator. Blue = up, orange = down. Smoother than Trend Catcher.
**Default**: OFF, period 3
**1-min /ES note**: Useful as a background trend filter. If Trend Tracer says downtrend, be skeptical of bullish confirmation signals. Period 3 is fine as a directional bias — not for timing entries.

#### Trend Catcher (toggle + period 1-5)
**Mechanism**: Early trend detection. More reactive than Trend Tracer. More signals, more noise.
**Default**: OFF, period 3
**1-min /ES note**: Good for catching the start of a move on 1-min. Period 2 for maximum reactivity. Be aware it will flip frequently during chop — combine with Oscillator Matrix confluence to filter.

#### Neo Cloud (toggle + period 1-5)
**Mechanism**: Gradient cloud similar to Ichimoku. Support/resistance from cloud edges.
**Default**: OFF, period 2
**1-min /ES note**: Adds visual weight to the chart. The cloud edges function as dynamic S/R. If you already have Smart Trail + Trend Catcher, Neo Cloud may be redundant visual noise. Consider adding AFTER you're comfortable with the other overlays.

#### Reversal Zones (toggle + period 1-5)
**Mechanism**: Upper/lower bands identifying potential tops and bottoms.
**Default**: OFF, period 3
**1-min /ES note**: More effective during ranging than trending. On 1-min /ES during trend days, price will blow through these zones. During chop/rotation days, they're very useful for fading extremes. Consider enabling on range-bound days and disabling on trend days — or leave off until you can identify the day type.

### Candle Coloring

#### Candle Coloring (dropdown)
**Mechanism**: Overrides candle colors to reflect indicator state.
**Default**: Confirmation Simple
**Options**: Confirmation Simple (binary trend color), Confirmation Gradient (intensity by strength), Contrarian Gradient (intensity by reversal proximity), None.
**1-min /ES note**: Confirmation Gradient gives you at-a-glance trend strength without reading numbers. Bright = strong trend, dim = weakening. Useful on 1-min where you're scanning fast.

### TP/SL Section

#### TP/SL Levels (dropdown)
**Mechanism**: Which indicator trigger generates take-profit and stop-loss levels.
**Default**: None
**1-min /ES note**: Skip during audit. Configure after signals and overlays are dialed in.

### Dashboard

#### Dashboard components
**Mechanism**: Information panel on the chart showing derived metrics.
**Defaults**: Location Bottom Right, Size Tiny, Trend Strength ON, Volatility OFF, Squeeze OFF, Volume Sentiment OFF
**1-min /ES note**: Enable Volatility and Volume Sentiment. /ES volatility shifts intraday (open vs. midday vs. close) and volume sentiment confirms directional conviction. Squeeze detection (Bollinger inside Keltner) can signal upcoming breakouts.

### Presets
**Available**: Trend Trader, Scalper, Swing Trader, Contrarian Trader
**Note**: Presets override your manual settings. Useful for initial exploration but once you've tuned individual settings, don't use presets — they'll wipe your work.

---

## Price Action Concepts — Settings Audit

### Market Structure Section

#### Internal (dropdown + length)
**Mechanism**: Short-term swing detection. Identifies BOS and CHoCH on internal structure.
**Default**: All, length 5
**Dropdown options**: All, CHoCH (All), CHoCH+, CHoCH, BOS, None
**Length trade-off on 1-min /ES**:
| Value | Behavior |
|-------|----------|
| 3-5 | Very granular. Every minor swing labeled. On 1-min /ES, you'll see internal structure changes every few minutes |
| 6-10 | Moderate filtering. Reduces noise but may miss fast reversals |
| 11-20 | Only significant internal swings. Most useful if you're using swing structure as primary |

**1-min /ES note**: Length 5 (default) catches the micro-structure. If the chart is too cluttered with BOS/CHoCH labels, increase to 7-8 or filter the dropdown to show only CHoCH (which is what matters most for reversals).

#### Swing (dropdown + length)
**Mechanism**: Higher-timeframe structure overlay. Identifies major BOS and CHoCH.
**Default**: All, length 50
**Length on 1-min /ES**: Length 50 = roughly 50-minute swing lookback. This gives you the "big picture" structure within the 1-min chart. Raising to 75-100 captures 1-2 hour swings.
**Note**: The power of having both internal and swing is the multi-timeframe view without switching charts. Internal for timing, swing for directional bias.

#### Timeframe
**Default**: Chart
**Note**: Can pull higher-TF structure onto 1-min chart. Useful for seeing 5-min or 15-min structure without switching. Leave at Chart initially — add MTF after baseline.

#### Show Swing High/Low (toggle)
**Default**: false
**Note**: Labels swing points with HH/HL/LH/LL. Useful for learning to read structure. Once you internalize the pattern, you may disable to reduce clutter.

#### Show Strong/Weak HL (toggle)
**Default**: false
**Mechanism**: Uses relative volume to assess whether a high/low is structurally strong or weak.
**1-min /ES note**: Useful information — strong highs are harder to break, weak highs are liquidity targets. Enable.

#### Color Candles (toggle)
**Default**: false
**Note**: Colors candles by current structure state (CHoCH vs BOS, bullish vs bearish). If you're already using S&O candle coloring, enabling this creates a conflict. Pick one.

### Volumetric Order Blocks Section

#### Show Last (toggle + count)
**Default**: true, 5
**Mechanism**: How many recent order blocks to display.
**1-min /ES note**: 5 is good for a clean chart. If you want more context (especially during high-activity periods), try 7-8. More than 10 clutters the chart.

#### Internal Buy/Sell Activity (toggle)
**Default**: true
**Mechanism**: Shows green/red bars inside the OB revealing whether buyers or sellers dominated during its formation.
**1-min /ES note**: **Keep ON.** This is the "volumetric" part. An order block where activity aligns with block type (bullish OB with green bars) is higher quality than one with mixed signals.

#### Show Breakers (toggle)
**Default**: false
**Mechanism**: Shows previously mitigated OBs that price may revisit as opposite S/R.
**1-min /ES note**: **Turn ON.** Breaker blocks on /ES 1-min frequently act as re-entry zones after a structure break. Missing these means missing high-probability levels.

#### Length (numerical)
**Default**: 5
**Mechanism**: Swing detection sensitivity for OB identification.
**1-min /ES note**: Same logic as Internal structure length. 5 catches more blocks, higher values = fewer, larger blocks.

#### Mitigation Method (dropdown)
**Default**: Close
**Options**: Close (price close crosses OB edge), Wick (any touch invalidates), Average (price crosses midpoint).
**1-min /ES note**: Close is conservative — the block survives wicks into it. This is correct for /ES where wicks through a level and reversal (grab) are common. Wick mitigation removes blocks too aggressively. Average is a middle ground.

#### Show Metrics (toggle)
**Default**: true
**Note**: Volume data on blocks. Keep on — larger volume blocks are stronger.

#### Show Mid-Line (toggle)
**Default**: true
**Note**: Average price within block. Useful as an entry target — price reaching OB midline is a common reaction point.

#### Hide Overlap (toggle)
**Default**: true
**Note**: Removes older blocks that overlap with newer ones. Keep on for chart clarity.

### Liquidity Concepts Section

#### Trend Lines (toggle + count)
**Default**: OFF, 5
**Mechanism**: Linear liquidity zones. Blue = support, red = resistance. Breaking the zone edge suggests reversal.
**1-min /ES note**: Can be useful but adds lines to an already busy chart. Enable after you're comfortable with OBs and structure.

#### Patterns (toggle + sensitivity)
**Default**: OFF, sensitivity 5
**Mechanism**: Automated chart pattern detection (triangles, H&S, double tops, etc.).
**1-min /ES note**: Pattern detection on 1-min is generally noisy. These patterns are more reliable on 5-15 min. Leave OFF on 1-min unless you're specifically looking for them.

#### Equal H&L (toggle + term)
**Default**: OFF, Short-Term
**Mechanism**: Identifies price levels where multiple swing highs or lows have formed at the same price — liquidity pools.
**1-min /ES note**: Equal highs/lows are liquidity targets that smart money hunts. Useful concept but can add clutter. Enable after structure and OBs are dialed in.

#### Liquidity Grabs (toggle)
**Default**: OFF
**Mechanism**: Highlights candles where price swept a high/low and reversed (the "grab").
**1-min /ES note**: **Enable.** Liquidity grabs on 1-min /ES are one of the most reliable reversal patterns. A bullish grab (sweep below a low, close back above) at a bullish OB is a high-confluence setup.

### Imbalance Concepts Section

#### Toggle + Type
**Default**: OFF, FVG
**Mechanism**: Highlights price areas with supply/demand disparity.
**1-min /ES note**: FVGs (Fair Value Gaps) are the primary type to enable. On 1-min /ES, unfilled FVGs act as magnets — price tends to return to fill them. This gives you targets.

#### Mitigation Method
**Default**: Close
**Options**: Close, Wick, Average, None
**Note**: Close = FVG stays visible until price closes through it. Conservative. None = FVGs stay visible forever (historical reference). For 1-min, Close or Average.

#### Extend (bars)
**Default**: 10
**Note**: How far the FVG box extends forward. 10 bars = 10 minutes on 1-min. Increase if you want FVGs visible longer.

#### Volatility Threshold
**Default**: 0
**Mechanism**: Filters out small FVGs. Higher value = only significant gaps shown.
**1-min /ES note**: At 0, you see every FVG including tiny ones. Start at 0 to see the full picture. If chart gets cluttered, increase to 1-2 to show only meaningful gaps.

### Premium & Discount Zones

#### Toggle
**Default**: OFF
**Mechanism**: Divides the current price range into premium (upper), equilibrium (middle), and discount (lower) zones.
**1-min /ES note**: Powerful contextual filter. Bullish signals in the discount zone are higher probability. Bearish signals in premium are higher probability. **Enable.**

### Previous Highs & Lows

#### Daily/Weekly/Monthly/Quarterly
**Default**: All OFF
**1-min /ES note**: **Enable Daily.** Yesterday's high and low are critical reference levels for intraday /ES. Weekly and monthly are useful for bigger-picture context but less actionable on 1-min. Enable Daily at minimum.

### Fibonacci Retracements
**Note**: Audit after all other settings are dialed in. Fib levels are derivative of structure — need structure reading correct first.

---

## Cross-Indicator Coherence Check

After reviewing individual settings, assess these alignment questions:

### Timescale Alignment
- Is HyperWave Length (Osc Matrix) targeting the same trade duration as Signals Sensitivity (S&O)?
- If HyperWave is set for 3-minute swings but Signals Sensitivity targets 15-minute trends, the indicators will disagree constantly.

### Feature Overlap
- Are both Smart Trail (S&O) and order block mid-lines (PAC) marking the same levels? If so, one is redundant visual noise.
- Is candle coloring enabled on both S&O and PAC? Pick one source.

### Complementary Gaps
- Is the oscillator pane (Osc Matrix) providing information the on-chart indicators (S&O, PAC) cannot? It should — that's the point of a separate pane.
- Are PAC concepts (structure, OBs) providing level-based context that S&O signals lack? They should — S&O tells you when, PAC tells you where.

### Signal Density
- On a typical 1-min /ES chart during RTH, how many signals/labels/overlays are firing per 15-minute window?
- If the answer is "overwhelming," prioritize: Structure + OBs + Confluence Meter + Smart Trail. Everything else is secondary.
