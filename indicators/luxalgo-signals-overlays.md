# LuxAlgo Signals & Overlays

On-chart indicator providing signal generation, technical overlays, and dynamic features directly on the /ES 1-min price chart.

## Signal Modes

### Confirmation + Exits (Default)

Trend-following methodology. Validates entries within established trends.

- **Normal signals**: Generated during retracements within a trend
- **Strong (+) signals**: Align with current estimated trend direction (higher confidence)
- **Exit signals**: Blue crosses (bullish exit), orange crosses (bearish exit)
  - Always exit previous confirmations at profit
  - Multiple exits possible during extended trends (partial position management)
- Less lag than most trend-following methods, but still has inherent confirmation delay

### Contrarian + Exits

Reversal-seeking methodology. Opposes current trend.

- **Strong (+) signals**: Price is excessively overbought/oversold
- **Exit signals**: Same color coding as confirmation
  - Successive exits do NOT occur in contrarian mode
- Lower lag = faster entries BUT larger price variations = potentially higher losses
- Best suited for identifying major turning points, not scalp entries

### ML Signal Classifier

Adaptive threshold classifier rating signals 1-4.

**For Confirmation mode:**
- Ratings 1-2: Potential reversals or retracements (lower confidence continuation)
- Ratings 3-4: Trend continuation signals (higher confidence)

**For Contrarian mode:**
- Ratings 1-2: Early trends, lower reversal probability
- Ratings 3-4: Developed trends, higher reversal probability

**Filter setting**: Enter digits to show only those ratings (e.g., "34" shows only high-confidence signals). Default "1234" shows all.

**Critical**: Signals confirm only at next candle opening. Current-candle signals may repaint.

## Signal Settings

| Setting | Default | Notes |
|---------|---------|-------|
| Signal Mode | Confirmation + Exits | Or Contrarian + Exits, None |
| ML Signal Classifier | false | Enable for signal rating |
| Signals Sensitivity | 12 | 5-10 = short-term, 12 = medium, 20+ = long-term |
| ML Classifier Filter | 1234 | Which ratings to display |
| Autopilot Sensitivity | Off | Off, Short-Term, Medium-Term, Long-Term |

**Autopilot**: Dynamically adjusts sensitivity to market conditions. Most user-friendly auto-tuning option.

**Dashboard Optimal Sensitivity**: Backtests sensitivities 10-20 over most recent 250 bars. Displays recommended value. Requires 250+ bars history.

## Indicator Overlays

All overlays have sensitivity 1-5 (higher = longer-term). Default sensitivity is 3, except Neo Cloud (2).

### Smart Trail (Default: ON, Period: 3)
Adaptive trailing stop. Blue = support (uptrend), red = resistance (downtrend). Adjusts during price fluctuations within trend. Price above trail = uptrend, below = downtrend.

### Trend Tracer (Default: OFF, Period: 3)
Trend-following algorithm estimating underlying direction. Blue = uptrend, orange = downtrend. Functions as trailing support/resistance. Can filter confirmation signals by aligning with detected trend.

### Trend Catcher (Default: OFF, Period: 3)
Like Trend Tracer but more reactive — aims to detect very early trends. Blue = up, orange = down. More signals but more noise.

### Neo Cloud (Default: OFF, Period: 2)
Gradient cloud similar to Ichimoku. Brighter colors = older trends. Support during uptrends, resistance during downtrends. Enables precise entries at cloud edges.

### Reversal Zones (Default: OFF, Period: 3)
Upper/lower zones identifying tops and bottoms. More effective during ranging than trending. Useful for profit-taking and early entries alongside confirmation signals. During high volatility, price may temporarily exceed zones.

## Candle Coloring

| Option | Description |
|--------|-------------|
| Confirmation Simple | Basic trend color |
| Confirmation Gradient | Gradient intensity by trend strength |
| Contrarian Gradient | Gradient by reversal proximity |
| None | Default candle colors |

## Take Profit / Stop Loss

Displays 4 TP and 4 SL levels from a trigger condition.

**Trigger sources**: Signals, Smart Trail, Reversal Zones, Trend Catcher, Trend Tracer, Neo Cloud, Custom Alert Creator

**Distance setting** (default 5): Controls TP/SL spacing from price. Higher = wider levels.

Levels dynamically recalculate when price deviates significantly from extremes.

## Dashboard

| Setting | Default |
|---------|---------|
| Location | Bottom Right |
| Size | Tiny |
| Trend Strength | true |
| Volatility | false |
| Squeeze | false |
| Volume Sentiment | false |

**Recommendation**: Enable Volatility and Volume Sentiment for /ES context.

## Presets

| Preset | Best For |
|--------|----------|
| Trend Trader | Trend continuation entries |
| Scalper | Short-term reactive signals |
| Swing Trader | Longer holding periods |
| Contrarian Trader | Reversal detection |

## Custom Alert Creator

Conditions available: Signal type, ML Classifier, Smart Trail, Trend Tracer, Trend Catcher, Neo Cloud, Reversal Zones, Trend Strength, External (3 slots).

Same step/sequence/invalidation system as Oscillator Matrix.

## Recommended 1-Min /ES Starting Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Signal Mode | Confirmation + Exits | Start with trend-following for /ES |
| ML Signal Classifier | true | Enable — filter to "34" once comfortable |
| Signals Sensitivity | 12 | Default, tune down if too laggy on 1-min |
| Smart Trail | ON, Period 2 | Tighten for 1-min reactivity |
| Trend Catcher | ON, Period 2 | Early trend detection for fast timeframe |
| Trend Tracer | ON, Period 3 | Background trend direction filter |
| Reversal Zones | OFF initially | Enable after baseline established |
| Neo Cloud | OFF initially | Can add later for cloud support/resistance |
| Candle Coloring | Confirmation Gradient | Visual trend strength at a glance |
| Dashboard Volatility | true | /ES volatility context matters |
| Dashboard Volume Sentiment | true | Confirm directional conviction |
| Autopilot | Short-Term | Let it adapt to 1-min /ES conditions |

Starting points for live validation.
