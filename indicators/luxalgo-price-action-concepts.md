# LuxAlgo Price Action Concepts

On-chart indicator automating ICT/SMC-style price action analysis: market structure, order blocks, liquidity, imbalances, and premium/discount zones on /ES 1-min.

## Market Structure

Automates Break of Structure (BOS) and Change of Character (CHoCH) detection.

### Concepts

**BOS (Break of Structure)** — Trend continuation. Price breaks prior swing high (bullish BOS, new HH) or prior swing low (bearish BOS, new LL).

**CHoCH (Change of Character)** — Potential reversal. Price breaks prior swing low during uptrend (bullish CHoCH) or prior swing high during downtrend (bearish CHoCH).

**CHoCH+** — Supported CHoCH, preceded by early warning (failed higher high or failed lower low before the break). Higher confidence than leading CHoCH.

### Two Dimensions

| Dimension | Lookback | Display | Purpose |
|-----------|----------|---------|---------|
| Internal | 5-49 (default 5) | Dashed lines, small text | Short-term structure |
| Swing | 50-100 (default 50) | Solid lines, large text | Higher-timeframe structure |

### Swing Labels
- HH (Higher High), HL (Higher Low) — uptrend
- LH (Lower High), LL (Lower Low) — downtrend

### Settings

| Setting | Default | Notes |
|---------|---------|-------|
| Internal dropdown | All | All, CHoCH (All), CHoCH+, CHoCH, BOS, None |
| Internal length | 5 | Swing detection sensitivity |
| Swing dropdown | All | Same options |
| Swing length | 50 | Swing detection sensitivity |
| Timeframe | Chart | Can use higher TF |
| Show Swing High/Low | false | Labels swing points |
| Show Strong/Weak HL | false | Volume-based strength assessment |
| Color Candles | false | Colors by current structure state |

### Candle Colors
- Darker bullish = Bullish CHoCH active (reversal underway)
- Regular bullish = Bullish BOS active (trend continuing)
- Darker bearish = Bearish CHoCH active
- Regular bearish = Bearish BOS active

## Volumetric Order Blocks

Zones where informed participants accumulated orders. Function as support/resistance until broken.

### Types

**Bullish OB**: Near swing lows. Potential support. Invalidated when price closes below lower edge.

**Bearish OB**: Near swing highs. Potential resistance. Invalidated when price closes above upper edge.

**Breaker Blocks**: Previously mitigated OBs that price may revisit. Non-solid background. Bullish breakers clear above upper edge; bearish below lower edge.

### Internal Activity
Green bars = bullish activity within OB construction. Red = bearish. Reveals whether activity aligns with block type and exhaustion potential.

### Metrics
- Accumulated volume within the interval
- Percentage of total displayed OB volume
- Larger volume = stronger block

### Settings

| Setting | Default | Notes |
|---------|---------|-------|
| Show Last | true, 5 | Number of recent blocks displayed |
| Internal Buy/Sell Activity | true | Volume breakdown inside OB |
| Show Breakers | false | Previously mitigated blocks |
| Length | 5 | Swing detection sensitivity |
| Mitigation Method | Close | Close, Wick, or Average |
| Timeframe | Chart | MTF available |
| Show Metrics | true | Volume data on blocks |
| Show Mid-Line | true | Average price within block |
| Hide Overlap | true | Removes overlapping blocks |

### Mitigation Methods
| Method | Trigger |
|--------|---------|
| Close | Price close crosses opposite extremity |
| Wick | Price high/low touches extremity |
| Average | Price crosses block midpoint |

### MTF Order Blocks
Higher-TF blocks overlaid on 1-min. Price/volume values from source TF. Time placement may differ from source chart.

## Liquidity Concepts

### Liquidity Trendlines (Default: OFF)
Linear zones based on liquidity concentration. Blue = support, red = resistance. Breaking zone extremity suggests trend reversal. Display retrospectively.

### Pattern Detection (Default: OFF)
Automated detection: ascending/descending triangles, symmetrical triangles, broadening wedges, double tops/bottoms, head & shoulders (standard + inverted). Dashboard at top-right shows confirmed patterns (solid) or support/resistance (dashed).

### Equal Highs & Lows (Default: OFF)
Historical equal H/L from swing points. Suggests potential CHoCH/BOS and reversal zones.

### Liquidity Grabs (Default: OFF)
Highlights activity in high-liquidity areas.
- **Blue (bullish grab)**: Low to candle body minimum — potential bullish reversal in demand
- **Red (bearish grab)**: High to candle body maximum — potential bearish reversal in supply
- **Both simultaneously**: Market indecision

## Imbalance Concepts

Price areas where supply/demand disparity prevented fair-value trading. Price tends to return to fill these gaps.

### Types

| Type | Description |
|------|-------------|
| **FVG (Fair Value Gap)** | 3-candle pattern where outer wicks don't overlap middle body. Bullish: current low > high from 2 bars ago. Bearish: current high < low from 2 bars ago |
| **Inverse FVG** | Mitigated FVG becomes opposite signal. Bullish FVG mitigated → bearish inverse |
| **Double FVG** | Overlapping FVGs create balanced price range. Bullish: new bullish FVG overlaps previous bearish |
| **Volume Imbalance** | Adjacent candles with non-overlapping bodies but overlapping wicks |
| **Opening Gap** | Adjacent candles with non-overlapping wicks (empty price space) |

### Settings

| Setting | Default | Notes |
|---------|---------|-------|
| Toggle | false | Must enable manually |
| Type | FVG | FVG, Inverse FVG, Double FVG, Volume Imbalance, Opening Gap |
| Mitigation | Close | Close, Wick, Average |
| Timeframe | Chart | MTF available |
| Extend | 10 bars | How far imbalance box extends |
| Volatility Threshold | 0 | Filter small imbalances. Higher = only significant gaps |

## Premium & Discount Zones

Three price areas: premium (upper), equilibrium (middle), discount (lower).

**Key interpretation rule**: Bullish signals in discount zone have higher reversal probability. Bearish signals in premium zone have higher reversal probability. Signals at equilibrium are neutral.

**Settings**: Toggle (default false).

## Previous Highs & Lows

MTF reference levels: Daily, Weekly, Monthly, Quarterly, Day-of-Week.

| Level | Default | Line Styles |
|-------|---------|------------|
| Daily | false | Solid, dashed, dotted |
| Weekly | false | Solid, dashed, dotted |
| Monthly | false | Solid, dashed, dotted |
| Quarterly | false | Solid, dashed, dotted |

## Fibonacci Retracements

24 source options for top/bottom anchors including Internal/Swing High/Low, CHoCH levels, OB levels, imbalance levels, MTF highs/lows.

## Custom Alert Creator

Conditions: Market Structure (11 conditions), Order Block (12), Imbalance (15), Trendline, Pattern (11), Liquidity Grabs, Premium/Discount, Session, OB Volume, External (3).

Same step/sequence system as other LuxAlgo indicators.

## Recommended 1-Min /ES Starting Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Internal Structure | All, length 5 | See all internal BOS/CHoCH on 1-min |
| Swing Structure | All, length 50 | Higher structure context within 1-min |
| Order Blocks | ON, last 5 | Key S/R levels from informed flow |
| OB Mitigation | Close | Conservative invalidation |
| Internal Activity | ON | Volume breakdown is critical for /ES |
| Show Breakers | ON | Revisited levels matter on 1-min |
| Imbalances | ON, FVG | Fair value gaps are primary imbalance type |
| FVG Volatility Threshold | 0 | Start with all, increase if chart is cluttered |
| Liquidity Grabs | ON | Identifies sweep-and-reverse patterns |
| Premium/Discount | ON | Zone context for signal quality assessment |
| Equal H/L | OFF initially | Add after baseline — can be noisy |
| Patterns | OFF initially | More useful on higher TFs |
| Daily Previous H/L | ON | Key reference levels for /ES intraday |

Starting points for live validation.
