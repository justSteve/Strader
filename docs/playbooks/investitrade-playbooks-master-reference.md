# InvestiTrade Playbooks — Master Reference

> **Version:** 1.0.0 · **Updated:** June 2026 · **Author:** Steve
>
> A unified, GitHub‑ready reference combining full playbook summaries, a compact cheat‑sheet, a comparison matrix, and a workflow diagram for every IvesTi trading strategy.

---

## Table of Contents

1. [Overview](#overview)
2. [Full Playbook Summaries](#full-playbook-summaries)
   - [Playbook 1 — Momentum Breakout (MB)](#playbook-1--momentum-breakout-mb)
   - [Playbook 2 — Mean Reversion Fade (MRF)](#playbook-2--mean-reversion-fade-mrf)
   - [Playbook 3 — Trend Continuation Pullback (TCP)](#playbook-3--trend-continuation-pullback-tcp)
   - [Playbook 4 — Opening Range Breakout (ORB)](#playbook-4--opening-range-breakout-orb)
   - [Playbook 5 — Options Premium Harvest (OPH)](#playbook-5--options-premium-harvest-oph)
   - [Playbook 6 — Gap Fill (GF)](#playbook-6--gap-fill-gf)
3. [Cheat Sheet](#cheat-sheet)
4. [Comparison Matrix](#comparison-matrix)
5. [Workflow Diagrams](#workflow-diagrams)
   - [Master Trade Decision Tree](#master-trade-decision-tree)
   - [Pre-Market Routine](#pre-market-routine)
   - [Playbook Selection Flow](#playbook-selection-flow)
   - [Trade Lifecycle](#trade-lifecycle)
6. [Risk Management Rules](#risk-management-rules)
7. [Glossary](#glossary)

---

## Overview

<a name="overview"></a>

The **IvesTi Trade Playbook System** is a discretionary-rules framework that identifies high-probability setups across multiple market conditions. Each playbook is a self-contained strategy with defined entry criteria, exit rules, position-sizing logic, and invalidation conditions.

### Core Philosophy

| Principle | Description |
|---|---|
| **Rule-First** | Every trade follows a documented playbook — no discretionary freelancing |
| **Asymmetric Risk** | Target minimum 2:1 reward-to-risk on all setups |
| **Context Is King** | Market regime (trending/ranging/volatile) gates which playbook is active |
| **Journaling Required** | Every trade is logged with entry thesis, screenshots, and outcome |

### Trading Hours & Sessions

| Session | Time (CT) | Notes |
|---|---|---|
| Pre-Market Prep | 8:00 – 9:25 AM | Watchlist build, news scan, level marking |
| Opening Session | 9:30 – 10:30 AM | ORB, Momentum Breakout active |
| Mid-Morning | 10:30 AM – 12:00 PM | Trend Continuation, Gap Fill setups |
| Lunch Chop | 12:00 – 1:00 PM | **Avoid** — low probability, wide spreads |
| Afternoon Session | 1:00 – 3:00 PM | Mean Reversion, Options Premium setups |
| Power Hour | 3:00 – 4:00 PM | Trend Continuation, manage open positions |

---

## Full Playbook Summaries

<a name="full-playbook-summaries"></a>

---

### Playbook 1 — Momentum Breakout (MB)

<a name="playbook-1--momentum-breakout-mb"></a>

**Category:** Breakout · **Session:** Opening / Power Hour · **Timeframe:** 1 min, 5 min, 15 min

#### Thesis

Price consolidates near a significant level (prior day high/low, VWAP, key round number) then breaks out with elevated volume, signaling institutional participation and directional conviction.

#### Setup Requirements

- [ ] Price approaching a **clearly defined resistance or support level** (tested ≥ 2x prior)
- [ ] **Relative volume (RVOL) ≥ 1.5x** the 20-day average at the candle of breakout
- [ ] Breakout candle body fills **≥ 60%** of candle range (no long wicks dominating)
- [ ] **Market regime:** SPY trending in same direction, or sector confirming
- [ ] **No major earnings** within 48 hours
- [ ] Avoid setups within **30 min of Fed announcements or economic data**

#### Entry Rules

| Type | Trigger | Notes |
|---|---|---|
| **Aggressive** | Break of the level on a 1-min close | Higher slippage risk; best in fast tape |
| **Conservative** | First pullback to broken level, hold confirmed | Lower fill rate; better R/R |
| **Limit Entry** | Pre-placed limit at +0.05 above breakout level | Works in pre-planned setups |

#### Stop Placement

- **Hard stop:** Below the consolidation low (for longs) / above consolidation high (for shorts)
- **Minimum stop distance:** 0.5 ATR to avoid noise stop-outs
- **Max stop:** 1.5 ATR — if level requires wider, skip the trade

#### Profit Targets

| Target | Level | Action |
|---|---|---|
| T1 | 1:1 R/R | Trim 40% of position; move stop to breakeven |
| T2 | 2:1 R/R | Trim another 35% of position |
| T3 | 3:1 R/R or measured move | Exit remaining runner |

#### Invalidation / Skip Conditions

- Breakout immediately reverses back inside consolidation (bull/bear trap)
- RVOL drops below 1.0x within 2 candles of breakout
- SPY reversing hard against the setup direction
- Multiple failed breakout attempts in the same session

#### Position Sizing

```
Risk per trade = Account × 0.5%
Shares = Risk per trade ÷ (Entry − Stop)
Max position = Account × 5% of capital at risk per sector
```

#### Sample Trade Log Entry

| Field | Value |
|---|---|
| Ticker | — |
| Date | — |
| Playbook | MB |
| Entry | — |
| Stop | — |
| T1 / T2 / T3 | — / — / — |
| RVOL at Entry | — |
| Outcome | Win / Loss / Breakeven |
| Notes | — |

---

### Playbook 2 — Mean Reversion Fade (MRF)

<a name="playbook-2--mean-reversion-fade-mrf"></a>

**Category:** Counter-Trend · **Session:** Afternoon · **Timeframe:** 5 min, 15 min

#### Thesis

After an extended parabolic move, price becomes statistically overextended relative to key anchors (VWAP, 20 EMA, Bollinger Bands). A fade captures the snap-back to the mean with defined risk at the extreme.

#### Setup Requirements

- [ ] Price **≥ 2.5 standard deviations** from VWAP (or outside upper/lower Bollinger Band on 5-min)
- [ ] RSI(14) **≥ 80** (overbought fade) or **≤ 20** (oversold fade) on 5-min chart
- [ ] **RVOL declining** — the move is exhausting, not accelerating
- [ ] At least **one reversal candle** (doji, hammer, shooting star, engulfing) at the extreme
- [ ] Market regime: SPY **not** making new intraday highs (for short fades) or new lows (for long fades)
- [ ] Minimum **$5M average daily dollar volume** on the ticker

#### Entry Rules

| Type | Trigger |
|---|---|
| **Standard** | Break of the reversal candle's opposite extreme (e.g., break of doji low for short) |
| **Aggressive** | Enter reversal candle body on momentum shift with tight stop |

#### Stop Placement

- Stop **above/below the candle wick extreme** of the reversal candle
- Absolute max: 1.0 ATR from entry; if wider, skip

#### Profit Targets

| Target | Level |
|---|---|
| T1 | Return to VWAP |
| T2 | 20 EMA on 5-min |
| T3 | Previous consolidation area |

#### Key Risk Warnings

> ⚠️ **Never fade a momentum continuation in a strong trending market.** Mean reversion only works in ranging or slightly trending conditions. Check SPY 15-min trend before fading any individual stock.

> ⚠️ **Do NOT use this playbook on low-float, news-driven momo stocks.** The squeeze can continue far longer than statistical models predict.

#### Invalidation

- New candle makes a fresh extreme beyond the reversal candle
- Catalyst (news, PR) dropped mid-move — exit immediately
- RVOL spikes again on breakout candle — reversal is failing

---

### Playbook 3 — Trend Continuation Pullback (TCP)

<a name="playbook-3--trend-continuation-pullback-tcp"></a>

**Category:** Trend · **Session:** Mid-Morning / Afternoon · **Timeframe:** 5 min, 15 min, Daily

#### Thesis

In a clearly established trend, price pulls back to a dynamic support (rising/falling EMA, VWAP, prior breakout level) and resumes in the trend direction. Entry on the pullback captures the continuation move at improved R/R.

#### Setup Requirements

- [ ] Clear trend: **Higher highs & higher lows** (uptrend) or lower highs & lower lows (downtrend) on the 15-min chart
- [ ] Price pulled back to the **8 EMA, 20 EMA, or VWAP** on the 5-min chart without violating trend structure
- [ ] **Pullback is orderly** — low RVOL, small candles (consolidation, not distribution)
- [ ] Entry trigger: **Resumption candle** with RVOL uptick breaks the pullback high/low
- [ ] SPY or sector ETF in same trend direction

#### EMA Stack Confirmation (Uptrend Example)

```
Price > 8 EMA > 20 EMA > 50 EMA   ✅ Strong alignment
Price > 8 EMA > 20 EMA            ✅ Valid
Price < 20 EMA but > 50 EMA       ⚠️  Use caution; reduce size
Price < 50 EMA                    ❌  Skip — trend may be broken
```

#### Entry, Stop, Targets

| Parameter | Rule |
|---|---|
| Entry | Break of pullback candle in trend direction with volume |
| Stop | Below pullback low (longs) / above pullback high (shorts); must hold EMA |
| T1 | Prior swing high/low |
| T2 | 2:1 R/R measured from entry |
| T3 | Trend channel top/bottom or daily resistance |

#### Scaling Strategy

- Enter **full size** on initial trigger
- If T1 is hit, trail stop to entry (breakeven)
- If T2 is hit, trail stop to T1 level
- Let the runner work until trend structure breaks or T3 is hit

---

### Playbook 4 — Opening Range Breakout (ORB)

<a name="playbook-4--opening-range-breakout-orb"></a>

**Category:** Opening Session · **Session:** 9:30–10:00 AM CT · **Timeframe:** 1 min, 5 min

#### Thesis

The first 15–30 minutes of trading define an "opening range." A decisive break of that range with volume signals institutional intent for the session and provides a high-probability directional trade.

#### Opening Range Definitions

| ORB Type | Range Window | Notes |
|---|---|---|
| ORB-5 | First 5 minutes | Aggressive; more false breakouts |
| ORB-15 | First 15 minutes | **Preferred** — balances speed and reliability |
| ORB-30 | First 30 minutes | Conservative; stronger signal |

#### Setup Requirements

- [ ] Ticker on pre-market watchlist with **pre-market volume ≥ 50k shares** traded
- [ ] Gap > 0.5% or meaningful pre-market catalyst (earnings, news, analyst action)
- [ ] Opening range height (high − low) is **≤ 3% of price** — if too wide, skip
- [ ] Breakout candle closes **fully outside** the opening range
- [ ] RVOL **≥ 2.0x** on breakout candle

#### Entry Rules

| Direction | Entry Trigger |
|---|---|
| Long | Break and close above ORB high |
| Short | Break and close below ORB low |

- Preferred: Enter on **first pullback to broken ORB level** after initial breakout
- Aggressive: Enter immediately on breakout candle close

#### Stop & Targets

| Parameter | Rule |
|---|---|
| Stop | Midpoint of the opening range |
| T1 | 1x the opening range height projected from breakout |
| T2 | 2x the opening range height |
| T3 | Pre-market high (long) / pre-market low (short) |

#### Session Context Rules

- **Gap Up + ORB Long** = strongest combo; full size
- **Gap Down + ORB Short** = strong; full size
- **Gap Up + ORB Short** = fade setup; reduce to half size
- **Flat Open + ORB** = lower conviction; reduce to half size

---

### Playbook 5 — Options Premium Harvest (OPH)

<a name="playbook-5--options-premium-harvest-oph"></a>

**Category:** Options · **Session:** Any · **Timeframe:** Daily (position) · **Holding Period:** 1–21 days

#### Thesis

Collect theta decay by selling options premium in high implied volatility environments where IV is likely to revert to the mean. The statistical edge comes from IV overpricing realized volatility approximately 70% of the time.

#### Strategy Variants

| Strategy | Structure | Best In |
|---|---|---|
| **Cash-Secured Put (CSP)** | Sell OTM put, secured by cash | Bullish or neutral bias |
| **Covered Call (CC)** | Sell OTM call against long stock | Neutral to slightly bullish |
| **Iron Condor (IC)** | Sell OTM call + OTM put spreads | Low trend, high IV rank |
| **Bull Put Spread (BPS)** | Sell put, buy lower put for defined risk | Bullish with defined risk |
| **Bear Call Spread (BCS)** | Sell call, buy higher call | Bearish with defined risk |

#### Strike Selection Rules

| Parameter | Rule |
|---|---|
| **IV Rank (IVR)** | Enter only when IVR ≥ 40 (prefer ≥ 60) |
| **Delta of short strike** | 0.20–0.30 delta (70–80% probability OTM) |
| **Days to Expiration (DTE)** | 21–45 DTE at entry |
| **Target premium** | ≥ 1/3 of the width of the spread (for spreads) |
| **Bid/Ask spread** | ≤ $0.05 per leg for liquid underlyings |

#### Management Rules

| Condition | Action |
|---|---|
| Profit reaches **50% of max credit** | Close the position (do not wait for expiration) |
| Trade reaches **21 DTE** | Evaluate rolling or closing |
| Loss reaches **2x credit received** | Close for a defined loss |
| Underlying makes sharp directional move | Assess delta exposure; roll or close |

#### Underlying Criteria

- **Liquid ETFs preferred:** SPY, QQQ, IWM, GLD, SLV, TLT
- **Individual stocks:** Only with avg daily volume ≥ 1M shares and liquid options chain
- **Avoid:** Earnings within the holding period, biotech binary events

#### Risk Per Trade

```
Max risk per OPH position = Account × 2%
For spreads: Max loss = width − credit received
For naked/CSP: Max loss = (Strike − 0) − Credit received (use margin requirement as proxy)
```

---

### Playbook 6 — Gap Fill (GF)

<a name="playbook-6--gap-fill-gf"></a>

**Category:** Mean Reversion · **Session:** Mid-Morning · **Timeframe:** 5 min, 15 min

#### Thesis

Price gaps create unfilled price "voids" on the chart. The market frequently revisits and fills these gaps, especially when the gap is not driven by a fundamental catalyst. Gap fill trades exploit this statistical tendency.

#### Gap Classification

| Type | Description | Fill Probability | Notes |
|---|---|---|---|
| **Common Gap** | No catalyst; routine price action | ~75% fill same day | High probability; take the trade |
| **Breakaway Gap** | On major catalyst or breakout | ~30% fill | Low probability; avoid or reduce size |
| **Continuation Gap** | Mid-trend, strong momentum | ~35% fill | Avoid as standalone GF trade |
| **Exhaustion Gap** | End of trend, capitulation move | ~65% fill | Valid but wait for reversal confirmation |

#### Setup Requirements

- [ ] Gap is **≥ 0.5% but ≤ 5%** of prior close — very large gaps are breakaway candidates
- [ ] Gap is a **common or exhaustion type** (no major catalyst)
- [ ] Price has begun reverting toward the gap — at least one candle body toward fill
- [ ] RVOL is declining from gap open (fading interest in gap direction)
- [ ] SPY is not trending hard in gap direction

#### Entry, Stop, Targets

| Parameter | Rule |
|---|---|
| Entry | On first 5-min candle that shows reversal toward gap |
| Stop | Beyond the gap open extreme (the furthest point from fill) |
| T1 | 50% of gap filled |
| T2 | Full gap fill (prior close) |
| T3 | Prior day close + small extension if momentum continues |

---

## Cheat Sheet

<a name="cheat-sheet"></a>

> Quick-reference card for pre-market prep and in-session decision making.

### Setup Quick-Reference

| Playbook | Acronym | Session | Direction | Must-Have |
|---|---|---|---|---|
| Momentum Breakout | MB | Open / Power Hour | Long or Short | RVOL ≥ 1.5x; level tested ≥ 2x |
| Mean Reversion Fade | MRF | Afternoon | Counter-trend | RSI ≥ 80 or ≤ 20; RVOL declining |
| Trend Continuation Pullback | TCP | Mid-Morning / PM | With trend | EMA stack aligned; pullback low-volume |
| Opening Range Breakout | ORB | 9:30–10:00 AM | Long or Short | RVOL ≥ 2.0x; ORB ≤ 3% width |
| Options Premium Harvest | OPH | Any | Neutral / defined | IVR ≥ 40; 21–45 DTE; 0.20–0.30 delta |
| Gap Fill | GF | Mid-Morning | Toward gap | Common/exhaustion gap; RVOL declining |

### Entry Trigger Summary

| Playbook | Long Entry | Short Entry |
|---|---|---|
| MB | Break + close above resistance | Break + close below support |
| MRF | Break of reversal candle high (short fade's low) | Break of reversal candle low (long fade's high) |
| TCP | Break of pullback high on volume | Break of pullback low on volume |
| ORB | Close above ORB high | Close below ORB low |
| OPH | Sell put / put spread when IVR high | Sell call / call spread when IVR high |
| GF | First candle reverting toward gap (long) | First candle reverting toward gap (short) |

### Stop Rules Snapshot

| Playbook | Stop Location |
|---|---|
| MB | Below consolidation low / above consolidation high; max 1.5 ATR |
| MRF | Beyond wick extreme of reversal candle; max 1.0 ATR |
| TCP | Below pullback low (long); above pullback high (short) |
| ORB | ORB midpoint |
| OPH | 2× credit received (loss limit); close at 21 DTE |
| GF | Beyond gap open extreme |

### Risk Management Quick Rules

```
Max daily loss limit:     Account × 2%    → STOP trading for the day
Max per-trade risk:       Account × 0.5%  → Equities/ORB/MB/TCP/MRF/GF
Max per-trade risk (OPH): Account × 2.0%  → Options positions only
Max open positions:       5 simultaneous positions
Max sector concentration: 2 positions in same sector at once
```

### Pre-Trade Checklist (30-Second Version)

- [ ] Is this on my watchlist? (No random tickers)
- [ ] Which playbook does this match?
- [ ] Is market regime compatible with this playbook?
- [ ] Is risk within limits?
- [ ] Do I have a stop and two targets defined *before* entry?
- [ ] Am I in the correct session window for this setup?

---

## Comparison Matrix

<a name="comparison-matrix"></a>

### Strategy Attribute Matrix

| Attribute | MB | MRF | TCP | ORB | OPH | GF |
|---|---|---|---|---|---|---|
| **Directional** | Yes | Yes | Yes | Yes | No (neutral) | Yes |
| **Trend-following** | Partial | No | Yes | Partial | No | No |
| **Counter-trend** | No | Yes | No | No | Partial | Yes |
| **Options-based** | No | No | No | No | Yes | No |
| **Intraday** | Yes | Yes | Yes | Yes | No | Yes |
| **Swing / Positional** | No | No | Partial | No | Yes | No |
| **Complexity** | Low | Medium | Low | Low | High | Low |
| **Speed of setup** | Fast | Medium | Medium | Very Fast | Slow/planned | Medium |
| **Avg hold time** | 5 min–2 hrs | 10 min–1 hr | 30 min–4 hrs | 15 min–3 hrs | 7–21 days | 15 min–2 hrs |

### Win-Rate & R/R Profile (Historical Targets)

| Playbook | Target Win Rate | Target Avg R/R | Notes |
|---|---|---|---|
| MB | 45–55% | 2.5:1 | Lower win rate offset by large winners |
| MRF | 55–65% | 1.5:1 | Higher win rate; smaller average win |
| TCP | 50–60% | 2.5:1 | Trend alignment boosts win rate |
| ORB | 45–55% | 2.0:1 | Strong when pre-market catalyst present |
| OPH | 65–75% | 0.5:1 (per trade) | High win rate; loss when it hits is larger |
| GF | 55–65% | 1.5:1 | Only common/exhaustion gaps qualify |

### Market Regime Compatibility

| Market Condition | MB | MRF | TCP | ORB | OPH | GF |
|---|---|---|---|---|---|---|
| **Strong Uptrend** | ✅ Long | ❌ Avoid | ✅ Long | ✅ Long | ⚠️ Reduced | ⚠️ Gaps fill less |
| **Strong Downtrend** | ✅ Short | ❌ Avoid | ✅ Short | ✅ Short | ⚠️ Reduced | ⚠️ Gaps fill less |
| **Ranging / Choppy** | ⚠️ Reduce size | ✅ Best condition | ❌ Skip | ⚠️ Reduce | ✅ Best condition | ✅ Best condition |
| **High Volatility** | ⚠️ Widen stops | ❌ Very risky | ⚠️ Reduce | ⚠️ Wider ORB | ✅ Best (high IVR) | ❌ Erratic fills |
| **Low Volatility** | ❌ Few setups | ❌ No extension | ✅ Clean trends | ⚠️ Narrow ORB | ❌ Low IVR; skip | ✅ Clean fills |
| **News-Driven Day** | ⚠️ Catalyst MB ok | ❌ Avoid | ❌ Skip | ✅ News catalyst | ❌ Avoid binary | ⚠️ Breakaway gap risk |

> **Legend:** ✅ Strong fit · ⚠️ Use with caution / reduce size · ❌ Avoid

### Position Sizing Comparison

| Playbook | Risk % / Trade | Typical Hold | Max Positions |
|---|---|---|---|
| MB | 0.5% | Minutes–hours | 3 concurrent |
| MRF | 0.5% | Minutes–hours | 2 concurrent |
| TCP | 0.5% | Hours–day | 3 concurrent |
| ORB | 0.5% | Hours | 2 concurrent |
| OPH | 2.0% | Days–weeks | 5 concurrent |
| GF | 0.5% | Minutes–hours | 2 concurrent |

---

## Workflow Diagrams

<a name="workflow-diagrams"></a>

### Master Trade Decision Tree

<a name="master-trade-decision-tree"></a>

```
┌─────────────────────────────────────────────────────┐
│           POTENTIAL TRADE IDENTIFIED                │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
         ┌────────────────────────────┐
         │  On Pre-Market Watchlist?  │
         └────────────────────────────┘
              │                  │
             YES                 NO
              │                  │
              ▼                  ▼
   Continue to next step     ❌ SKIP — not in plan
              │
              ▼
     ┌─────────────────────────────┐
     │  Within valid session time? │
     └─────────────────────────────┘
              │                  │
             YES                 NO
              │                  │
              ▼                  ▼
   Continue to next step     ❌ WAIT or SKIP
              │
              ▼
     ┌──────────────────────────────────────────┐
     │  Which playbook does this setup match?   │
     └──────────────────────────────────────────┘
       │       │       │       │       │       │
       ▼       ▼       ▼       ▼       ▼       ▼
      MB     MRF     TCP     ORB     OPH      GF
       │       │       │       │       │       │
       └───────┴───────┴───────┴───────┴───────┘
                          │
                          ▼
            ┌─────────────────────────┐
            │  All checklist items ✅? │
            └─────────────────────────┘
                   │           │
                  YES          NO
                   │           │
                   ▼           ▼
        ┌─────────────────┐   ❌ SKIP — setup is invalid
        │ Risk within 0.5%│
        │  daily limit OK?│
        └─────────────────┘
               │       │
              YES       NO
               │       │
               ▼       ▼
          ✅ ENTER   ❌ REDUCE SIZE or SKIP
```

---

### Pre-Market Routine

<a name="pre-market-routine"></a>

```
08:00 AM ──► MARKET CONTEXT
             • SPY / QQQ futures direction & % move
             • VIX level (Low <15 | Med 15–25 | High >25)
             • Key economic releases today (note times)
             • Fed speakers or policy events

08:20 AM ──► NEWS SCAN
             • Earnings reports overnight
             • Sector/macro headlines
             • Pre-market movers > ±2%

08:40 AM ──► BUILD WATCHLIST (max 5–8 names)
             • Pre-market volume leaders
             • Stocks near key technical levels
             • Sector ETF alignment check
             • Note: Catalyst type → which playbook it may set up

09:00 AM ──► LEVEL MARKING
             • Prior day high / low
             • Pre-market high / low
             • Key weekly/monthly levels
             • VWAP (auto on open)
             • Opening range brackets (ORB-15 ready)

09:25 AM ──► FINAL CHECKS
             • Daily loss limit reset & reviewed
             • Max positions check (no open overnight risk)
             • Platform & orders verified
             • Journal open and ready

09:30 AM ──► MARKET OPEN — Execute only planned setups
```

---

### Playbook Selection Flow

<a name="playbook-selection-flow"></a>

```
START: Market opens / Setup spotted
          │
          ▼
    What time is it?
     ┌──────────────────────────────────────────────┐
     │ 9:30–10:00 AM → Consider ORB first           │
     │ 9:30–10:30 AM → MB is also active            │
     │ 10:30 AM–12:00 PM → TCP or GF               │
     │ 12:00–1:00 PM → LUNCH CHOP — stand aside     │
     │ 1:00–3:00 PM → MRF or OPH or TCP            │
     │ 3:00–4:00 PM → Power Hour MB or TCP          │
     └──────────────────────────────────────────────┘
          │
          ▼
    What is the market regime?
     ┌─────────────────────────────────────────────┐
     │ TRENDING (SPY making new highs/lows)        │
     │   → Prefer MB, TCP, ORB in trend direction  │
     │                                             │
     │ RANGING (SPY oscillating, no trend)         │
     │   → Prefer MRF, GF, OPH                    │
     │                                             │
     │ HIGH VOL / NEWS DRIVEN                      │
     │   → MB on catalyst, OPH if IVR spiked       │
     │   → Avoid MRF, GF in chaotic tape           │
     └─────────────────────────────────────────────┘
          │
          ▼
    What does the individual setup show?
     ┌─────────────────────────────────────────────┐
     │ Price breaking a key level on high RVOL?    │
     │   → MB or ORB                               │
     │                                             │
     │ Price extended, reversal candle forming?     │
     │   → MRF                                     │
     │                                             │
     │ Trend intact, low-RVOL pullback to EMA?     │
     │   → TCP                                     │
     │                                             │
     │ Gap open, no major catalyst, price turning? │
     │   → GF                                      │
     │                                             │
     │ IV Rank ≥ 40, neutral to mild directional?  │
     │   → OPH (plan spread or CSP)               │
     └─────────────────────────────────────────────┘
          │
          ▼
     Execute chosen playbook checklist → TRADE
```

---

### Trade Lifecycle

<a name="trade-lifecycle"></a>

```
  ┌──────────────────────────────────────────────────────────┐
  │                      TRADE LIFECYCLE                     │
  └──────────────────────────────────────────────────────────┘

  [1] PRE-TRADE PLANNING
       • Identify setup → match playbook
       • Mark entry, stop, T1, T2, T3
       • Calculate position size
       • Write trade thesis (1 sentence) in journal

  [2] ENTRY EXECUTION
       • Enter per playbook rules (aggressive vs conservative)
       • Set stop-loss order immediately after fill
       • Set T1 limit order

  [3] TRADE MANAGEMENT
       ┌──────────────────────────────────────┐
       │   Price hits T1                      │
       │   → Trim 40%, move stop to breakeven │
       │   → Set T2 limit order               │
       └──────────────────────────────────────┘
       ┌──────────────────────────────────────┐
       │   Price hits T2                      │
       │   → Trim 35%, trail stop to T1       │
       │   → Let runner work toward T3        │
       └──────────────────────────────────────┘
       ┌──────────────────────────────────────┐
       │   Price hits stop                    │
       │   → Full exit, no averaging down     │
       │   → Record loss in journal           │
       └──────────────────────────────────────┘

  [4] EXIT
       • All targets hit → full exit → record in journal
       • Stop hit → full exit → record in journal
       • End of session → close all intraday positions
       • OPH only: manage per DTE and P/L % rules

  [5] POST-TRADE REVIEW
       • Log: entry/exit price, R/R realized, playbook used
       • Screenshot: chart at entry and at exit
       • Rate: A (textbook) / B (valid but suboptimal) / C (should not have taken)
       • Note: What was done correctly? What would be done differently?
```

---

## Risk Management Rules

<a name="risk-management-rules"></a>

> These rules are **non-negotiable** and apply across all playbooks.

### Hard Limits

| Rule | Threshold | Action if Breached |
|---|---|---|
| Daily max loss | 2% of account | Stop trading for the rest of the day |
| Per-trade max risk | 0.5% of account (2% for OPH) | Do not enter if sizing exceeds this |
| Max open positions | 5 simultaneously | Wait for a position to close first |
| Max same-sector positions | 2 simultaneously | Diversify before adding |
| Consecutive losses (streak) | 3 in a row | Take a 30-min break; reassess |

### Behavior Rules

1. **Never average down** on a losing trade. Add only to winning trades (scale in on confirmations, not against you).
2. **Never move a stop away from price.** You may trail stops toward price (lock in gains), never away.
3. **Never risk more to "make back" a loss.** Daily loss limits are absolute.
4. **No FOMO entries.** If you missed the entry, wait for the next pullback or skip entirely.
5. **No trading during first 5 minutes** unless it is a pre-planned ORB setup.
6. **No trading during economic data releases** (NFP, FOMC, CPI) — exit open positions or bracket them before the release.

### Weekly & Monthly Reviews

| Review | Frequency | Key Questions |
|---|---|---|
| Trade Journal Review | Weekly (every Friday) | Win rate by playbook? Avg R/R? Recurring mistakes? |
| Equity Curve Check | Weekly | Is the curve trending up? Any drawdown > 5%? |
| Playbook Performance | Monthly | Which playbooks are positive expectancy? Which to pause? |
| Rule Compliance Audit | Monthly | % of trades that followed all checklist items? |

---

## Glossary

<a name="glossary"></a>

| Term | Definition |
|---|---|
| **ATR** | Average True Range — measures average daily price movement; used for stop sizing |
| **DTE** | Days to Expiration — used in options management |
| **EMA** | Exponential Moving Average — dynamic support/resistance level |
| **GF** | Gap Fill playbook |
| **IVR / IV Rank** | Implied Volatility Rank — percentile of current IV vs. past 52 weeks (0–100) |
| **MB** | Momentum Breakout playbook |
| **MRF** | Mean Reversion Fade playbook |
| **ORB** | Opening Range Breakout playbook |
| **OPH** | Options Premium Harvest playbook |
| **OTM** | Out of the Money — option with no intrinsic value |
| **R** | Risk unit — 1R = the amount risked on a trade; 2R = 2× that amount gained |
| **R/R** | Reward-to-Risk ratio |
| **RSI** | Relative Strength Index — momentum oscillator (0–100 scale) |
| **RVOL** | Relative Volume — current volume vs. average for the same time of day |
| **TCP** | Trend Continuation Pullback playbook |
| **VWAP** | Volume Weighted Average Price — intraday fair value anchor |

---

*IvesTi Trade Playbooks · Master Reference v1.0.0 · June 2026*
*For personal use in active trading. This document does not constitute financial advice.*