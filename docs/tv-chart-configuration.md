# TradingView Chart Configuration Guide

Primary instrument: SPX (or ES1! for futures reference)
All times: Central Time

---

## Tab 1: ORB Morning (8:30–10:00 CT)

**Purpose:** Opening Range Breakout detection and execution.

### Main Chart Pane — SPX 5-minute
- **LuxAlgo Ultimate ORB**
  - Session: 8:30–9:00 CT (30-min opening range) — start here, can tighten to 15-min after observation
  - Range source: High/Low (not Close)
  - Extension type: Standard (not Fibonacci — cleaner targets for your profile)
  - Show volume qualifier: ON (HV/LV labels are the primary filter)
  - Trailing stop: ON
  - Stop optimizer: ON (let it find the best ATR multiplier)
  - Hit rate dashboard: ON (visible confirmation of target reliability)
- **VWAP** (built-in)
  - Source: HLC3 (default)
  - Show bands: ON — 1st, 2nd, and 3rd standard deviations
  - Band colors: subtle (gray or dotted) so they don't compete with ORB levels
- **Session Volume Profile** (built-in)
  - Visible range: Session
  - Row size: 24 (enough detail without clutter)
  - Show POC: ON
  - Show Value Area: ON (70%)
  - Place on: Left side of chart
  - Opacity: low (background reference, not dominant)

### Lower Pane 1 — Cumulative Delta
- Add: "Cumulative Volume Delta" (search TV indicators — LuxAlgo has one, or use a well-rated community version)
- Display: histogram + line
- Purpose: confirm breakout conviction (delta in direction of break = real), spot divergences

### Lower Pane 2 — $TICK
- Symbol: USI:TICK (NYSE Tick Index)
- Chart type: Line or histogram
- Add horizontal lines at +800, -800, +1000, -1000
- Purpose: breadth confirmation for breakouts. Breakout + extreme $TICK = high conviction

### Chart Settings
- Pre-market data: OFF (ORB is about the regular session open)
- Scale: Auto

---

## Tab 2: Midday Structure (10:00–1:00 CT)

**Purpose:** Monitor consolidation formation, identify day type, prepare for afternoon plays. No trades in this window — observation only.

### Main Chart Pane — SPX 5-minute
- **LuxAlgo Price Action Concepts**
  - Show all levels: Liquidity levels, order blocks, fair value gaps
  - These define the consolidation range boundaries and reveal where trapped traders sit
- **VWAP + bands** (same settings as Tab 1)
  - During consolidation, price hugging VWAP confirms range-bound behavior
  - Departure from VWAP signals the sharp move may be starting
- **Market Profile / TPO**
  - Add: Search for "TPO" or "Market Profile" in TV indicators
  - Recommended: LuxAlgo's if available, or "Market Profile" by Tradingview built-in (under "Community Scripts" or indicator search)
  - Settings:
    - Session: Regular hours only
    - TPO size: 30 min (standard)
    - Show developing POC: ON
    - Show Value Area: ON
    - Show letters/blocks: personal preference — blocks are cleaner visually
  - What to watch:
    - **D-shape** forming = normal rotation day → flies are well-positioned
    - **P-shape** (fat top) = buying trend → flies risky if expecting a drop
    - **b-shape** (fat bottom) = selling trend → drop may not reverse
    - **Elongated/thin** = trend day, single prints forming → flies risky

### Lower Pane — $ADD (Advance/Decline)
- Symbol: USI:ADD
- Purpose: broad market health check. Deteriorating $ADD during consolidation warns that the afternoon drop may be sharper or less likely to reverse.

### Chart Settings
- This tab is a monitoring view — no indicators need alerting
- Keep it clean, reference only

---

## Tab 3: Butterfly Afternoon (1:00–3:00 CT)

**Purpose:** Identify the sharp late-day move, assess reversal probability, time butterfly entry.

### Main Chart Pane — SPX 2-minute
- Tighter timeframe than morning — moves happen fast in the final hours
- **LuxAlgo Price Action Concepts**
  - Same config as Tab 2 — trapped-trader levels are your reversal signals
  - Pay special attention to liquidity sweeps (price breaks a level then reverses — this IS the sharp drop + rally pattern)
- **VWAP + Standard Deviation Bands**
  - Key read: how far has the sharp drop pushed price from VWAP?
  - Drop to -2σ band = statistically extended, reversion setup
  - This is your butterfly entry zone confirmation
- **Session Volume Profile**
  - Same settings as Tab 1
  - Look for: the sharp drop moving into a LOW-volume node (fast travel) then hitting a HIGH-volume node (potential support/stall)
  - POC from earlier consolidation = the target for the rally back (center your butterfly here)

### Lower Pane 1 — Cumulative Delta (same indicator as Tab 1)
- **Critical here:** Watch for divergence during the sharp drop
- Price making new session lows BUT cumulative delta NOT making new lows = exhaustion
- This is the highest-probability reversal signal for your butterfly timing
- When you see divergence at a GEX support level → that's your entry

### Lower Pane 2 — $TICK
- Same config as Tab 1
- Extreme negative readings (-1000+) that start moderating = selling pressure exhausting
- $TICK turning positive while price is still near lows = reversal underway

### Chart Settings
- Extended hours: OFF
- Consider 1-minute chart if you want finer entry timing, but 2-minute reduces noise

---

## Tab 4: Reference / Internals (Optional)

**Purpose:** Quick-glance dashboard Steve can check without cluttering trading tabs.

### Layout: 4-pane grid (use TV's multi-chart layout)

| Pane | Symbol | Timeframe | Purpose |
|------|--------|-----------|---------|
| Top-left | VIX | 5-min | Fear gauge — rising VIX during the session = put buyers active |
| Top-right | /ES (ES1!) | 5-min with Volume Profile | Institutional futures flow, confirms or diverges from SPX |
| Bottom-left | $TICK | 5-min line | Breadth at a glance |
| Bottom-right | SPY or NVDA | 5-min | Mag 7 proxy — if NVDA is moving 3%+ it's dragging SPX |

This tab stays in the background. Strader will reference it and surface what matters — Steve only needs to look here if Strader flags something specific.

---

## Watchlist (right sidebar)

Keep a small watchlist visible across all tabs:

```
$SPX.X          — SPX index
/ES             — E-mini S&P futures
VIX             — Volatility index
NVDA            — Mag 7 bellwether
$TICK           — NYSE Tick (if not in a pane)
$ADD            — Advance/Decline (if not in a pane)
```

---

## GEX Levels

GEX is not a standard TV indicator — it comes from external sources (SpotGamma, Menthor Q, etc.). However GEX data is obtained:
- Plot key levels as horizontal lines on Tabs 1, 2, and 3
- Critical levels: Zero Gamma (flip point), Call Wall (resistance), Put Wall (support)
- These can be drawn manually or via a Pine Script that accepts manual input
- GEX levels are most actionable on Tab 3 — the butterfly entry depends on whether the sharp drop hits a GEX support level

---

## General TV Settings

- **Theme:** Dark (reduces eye strain during long sessions)
- **Timezone:** Exchange (ensures candles align with market hours)
- **Price scale:** Auto, right side
- **Crosshair:** Dot (less visual noise than full crosshair)
- **Magnet mode:** ON when drawing levels, OFF during trading

---

## What Strader Needs From You

1. Add these indicators to your TV setup when markets are closed (weekend is ideal)
2. Save each tab as a named layout (e.g., "ORB Morning", "Midday Structure", "Butterfly PM", "Internals")
3. During sessions, switch tabs as the day progresses — or keep them on separate monitors
4. When you tap in for a session, tell Strader which tab you're viewing so the pre-session read can reference what you're seeing
