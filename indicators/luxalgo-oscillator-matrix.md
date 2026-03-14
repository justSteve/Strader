# LuxAlgo Oscillator Matrix

Oscillator-pane indicator combining 6 components for trend following and reversal detection. Runs below the /ES 1-min chart.

## Components

### HyperWave

Normalized adaptive oscillator (0-100 scale) reflecting price trends with minimal noise.

**Settings:**
| Setting | Default | Notes |
|---------|---------|-------|
| Show HyperWave | true | Master toggle |
| HyperWave Length | 7 | Higher = longer-term trends. For 1-min /ES, keep low (5-10) |
| Signal | SMA | SMA (more responsive) or Trailing Stop (less noise, better at higher lengths) |
| Signal Length | 3 | Higher = smoother signal line |
| Colors | 80 | Transparency of area fill between wave and signal |

**Signals:**
- **Green dot**: HyperWave crosses above signal line (bullish turning point)
- **Red dot**: HyperWave crosses below signal line (bearish turning point)
- **Large green dot**: Cross above signal while HyperWave < 20 (oversold bullish — high value)
- **Large red dot**: Cross below signal while HyperWave > 80 (overbought bearish — high value)

**Interpretation:**
- HyperWave above signal = bullish bias
- HyperWave below signal = bearish bias
- Oversold/overbought turning points are the highest-confidence reversal signals
- Area between wave and signal line is color-coded for trend direction

### HyperWave Divergences

Real-time divergence detection between price and oscillator.

**Settings:**
| Setting | Default | Notes |
|---------|---------|-------|
| Divergence Sensitivity % | 10 | Lower = fewer, longer-term divergences. Higher = more, shorter-term |
| Show Divergences | true | On oscillator pane |
| Show Divergences On Chart | true | On price chart (max 500 lines, retrospective placement) |

**Signals:**
- **Blue lines**: Bullish divergence (price making lower lows, oscillator making higher lows)
- **Red lines**: Bearish divergence (price making higher highs, oscillator making lower highs)

**Interpretation:**
- Divergences warn of exhaustion, not immediate reversal
- Combine with reversal signals and confluence for confirmation
- Chart-displayed lines appear retrospectively, not at exact detection point

### Smart Money Flow

Detects trends based on market participant activity. Longer-duration signals than HyperWave.

**Settings:**
| Setting | Default | Notes |
|---------|---------|-------|
| Show Money Flow | true | Master toggle |
| Money Flow | 35 | Oscillator length. Higher = longer-term trends |
| Smooth | 6 | Smoothing intensity. Higher = smoother output |

**Components:**
- **Money Flow oscillator**: Center line at 50, with upper and lower thresholds
- **Overflow**: Excessive liquidity entering market — late participants piling in, often precedes reversal
- **Thresholds**: Two lines above/below 50 marking significant one-sided activity

**Interpretation:**
- Above upper threshold = significant bullish activity (one-sided)
- Below lower threshold = significant bearish activity (one-sided)
- Between thresholds = balanced/neutral
- **Overflow signals are reversal warnings** — excess liquidity = late money = potential exhaustion

### Reversal Signals

Trend reversal detection system displayed on oscillator pane.

**Settings:**
| Setting | Default | Notes |
|---------|---------|-------|
| Reversal Factor | 5 | 1-10. Higher = fewer detections (more selective) |
| Show Reversals | true | Toggle |

**Signal Types:**
- **Minor Reversal (-)**: Circles. Frequent. Short-term retracements, impulse tops/bottoms
- **Major Reversal (+)**: Triangles. Less frequent. Significant directional shifts

**Interpretation:**
- Minor reversals = tactical scalping signals on 1-min
- Major reversals = larger move developing, potentially multi-minute trend change
- Always confirm with confluence and Money Flow direction

### Confluence

Measures alignment between HyperWave and Money Flow.

**Settings:**
| Setting | Default | Notes |
|---------|---------|-------|
| Upper Confluence | true | Shows zone above 100 |
| Lower Confluence | true | Shows zone below 0 |
| Show Confluence Meter | false | Quantitative gauge |
| Meter Width | 3 | Line thickness |

**Confluence Zones (upper/lower):**
- **Darker green (upper)**: Both HyperWave AND Money Flow confirm uptrend (value = 2)
- **Brighter green (upper)**: Only one confirms uptrend (value = 1)
- **Value 0**: No confluence
- Mirror logic for lower/bearish zones

**Confluence Meter** tracks alignment across:
- HyperWave vs signal line
- HyperWave trend
- Money Flow trend
- Overflow conditions
- Divergences

Higher meter = stronger bullish alignment. Lower = stronger bearish.

**Interpretation:**
- **Strong confluence (2) + reversal signal = highest confidence trade**
- Weak confluence (1) = proceed with caution, look for additional confirmation
- No confluence (0) = mixed signals, stand aside or reduce size

## Custom Alert Creator

Multi-step conditional alert system. Each condition can be assigned to steps (1-9, All, Invalidate, OR) enabling sequential confluence detection.

**Available Conditions:**
- Money Flow (threshold crossings)
- Overflow (threshold crossings)
- HyperWave (turning points, overbought/oversold, threshold crossings)
- Reversals (minor/major, up/down)
- Divergences (bullish/bearish)
- Confluence (strong/weak bullish/bearish)
- Confluence Meter (threshold crossings)
- External conditions (3 available, OHLC comparisons)

**Sequence Control:**
- Maximum Step Interval: 10 bars (default) — resets if steps don't complete within this window
- Invalidation: None, On Step 1, On Any Repeated Step

## Recommended 1-Min /ES Starting Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| HyperWave Length | 7 | Default is good for 1-min reactivity |
| Signal | SMA | More responsive for fast timeframe |
| Signal Length | 3 | Keep tight for 1-min |
| Money Flow | 35 | Default captures intraday participant activity |
| Smooth | 6 | Default adequate |
| Reversal Factor | 5 | Start at default, increase if too noisy |
| Divergence Sensitivity % | 10 | Start at default |
| Show Confluence Meter | true | Turn ON — this is your primary confluence read |

These are starting points. Steve will validate against live /ES 1-min charts and we'll tune from there.
