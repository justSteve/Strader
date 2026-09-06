---
type: convention
title: "Strader Knowledge Bundle — Index"
description: "OKF entry point for the Strader Knowledge Bundle: type vocabulary and concept listing. Start here."
timestamp: 2026-07-19T13:05:36-05:00
---

# Strader Knowledge Bundle — Index

OKF v0.1 bundle. This file is the progressive-disclosure entry point;
bundle-level history in [log.md](log.md).

**This bundle is distilled knowledge ("what we know"). Beads are work
and decision history ("what we're doing"). Neither mirrors the other.**

## Type vocabulary

| type | meaning |
|------|---------|
| `convention` | An agreed practice — how we do a thing |
| `decision` | A settled choice with rationale |
| `runbook` | Ordered procedure for a recurring operation |
| `rule` | A binding constraint |
| `playbook` | Conditional strategy: when X, do Y (terminates in human judgment) |
| `reference` | How the outside world works — external methods and frameworks |
| `operator-profile` | Durable facts about Steve |

`reference` and `operator-profile` extend COO's v1 vocabulary; nothing
in it covered external domain knowledge or facts about the operator.

## Concepts

### convention

- [Drills as Code](drills-as-code.md) — Drills ship as self-contained runnable artifacts; agent session time is for judgment/review, not administering mechanics
- [Entitlements Registry](entitlements-registry.md) — Subscription/entitlement state lives in ONE file (`config/entitlements.yaml`), probed at statement time; docs point at it and never restate tiers or prices
- [Establish Before Abbreviate](establish-before-abbreviate.md) — Steve-facing writing must build context before compressing — no unestablished abbreviations or insight-shorthand
- [Fork Doctrine](fork-doctrine.md) — Enterprise forks repos to own/extend them, not just pin versions. Use local clones and editable installs, not pip from PyPI.
- [Probabilistic, Not Absolutist](probabilistic-not-absolutist.md) — Frame trading analysis as probabilistic edge, not proof/absolutism — stop over-hedging
- [Spell Out Bead References](spell-out-bead-references.md) — Never cite bead IDs as if they're common knowledge — every reference needs its title and one line of context; slow down for Steve
- [Stages, Not Beats](stages-not-beats.md) — Steve seizes on musical metaphors — the four-part setup sequence is "stages," never "beats"; fixed drill deck over fresh-data churn
- [WSL Distro Is Zgent](wsl-distro-is-zgent.md) — This session runs in WSL distro "Zgent", not "Ubuntu" — use \\wsl$\Zgent\ for Windows paths

### decision

- [Orderflow Mastery — the directive, and who owns it](orderflow-mastery-ownership.md) — `decision`, 2026-08-15: the 08-06 directive and its steers, kept here; ownership returned from COO to Strader by Steve's ruling (COO co-u58u2). Start here before resuming any orderflow work
- [The Counter-Dictum Program](counter-dictum-program.md) — **⚠ TABLED 2026-08-10 — UNDER CONSTRUCTION, DO NOT APPLY.** Draft charter for the orderflow/execution effort, parked by Steve. Do not cite it or design against it; its §5 measured numbers stand as measurement history only. Current focus is understanding GexBot's Orderflow dataset, guided by Freddy
- [Checkpoint Loop Discontinued](checkpoint-loop-discontinued.md) — The 30-min /checkpoint auto-save loop is discontinued (2026-07-13) — do not start it at session start
- [Databento Live Collection](databento-live-collection.md) — Databento forward-collection mode is LIVE tick stream (chosen over T+1 batch), via scripts/corpus_stream_databento.py
- [Grow Into Live Trading](grow-into-live-trading.md) — 8/1/2026 go-live is a hard start date but NOT full-size — graduated entry, permission to grow into the system
- [TradingView Chart Interface](tradingview-chart-interface.md) — There is no automated TradingView interface — MCP and the screenshot/Vision pipeline are both dead. Chart state comes from our own corpus; Pine is hand-pasted.

### operator-profile

- [Direction Inversion Watch](direction-inversion-watch.md) — Steve's known error mode — direction/sign inversions that stay internally consistent; he asked Strader to watch for them
- [Steve Is the Risk Authority, Not the Arbiter of Price Action](steve-risk-authority-not-pa-arbiter.md) — sole risk/sizing authority; confirmation belongs to hindsight measurement, never to his chair time
- [Perceptual Profile](perceptual-profile.md) — Steve self-reports above-average (not freak-level) perception of momentum and angles — factor into drill design
- [Trading Since 2021](trading-since-2021.md) — Steve has been trading only since 2021 — don't write as if he carries decades of market experience

### playbook

- [Buying Movement — Delta-First](buying-movement-delta-first.md) — Steve trades flies and singles delta-first not theta-first; singles = short-hold move-capture, flies = V-dump entry with a scaled exit and a runner left for the pin
- [Directional GEX Butterflies](directional-gex-butterflies.md) — Steve trades late-day flies DIRECTIONALLY centered on the GEX target, not neutral/ATM theta-harvest
- [ORB Playbook](orb-playbook.md) — Strategy 2, the mechanical 8:30–10:00 CT opening range breakout on LuxAlgo Ultimate ORB: HV signals only, ATR trail, take Target 1, one trade per morning
- [PAC Order Blocks for Strike Centering](pac-order-blocks-for-strike-centering.md) — LuxAlgo PAC order blocks are Steve's primary tool for butterfly strike centering — more precise than Mancini levels alone
- [Reclaim Under the Lid](reclaim-under-the-lid.md) — Named setup from Carmine's 2026-08-19 7739 trades: Mancini's FBD shape on a level with history, plus a stepping-down seller lid and absorbed dips under the reclaim point, thin volume above to the first target; six conditions, five mechanical
- [Selective Range Scalping](selective-range-scalping.md) — Strategy 3, **exploratory** — A+ PAC level bounces only, 2–3 per session max, 3–5 SPX point targets sized to beat option spread friction
- [Singles as Futures Proxy](singles-as-futures-proxy.md) — Steve trades 0DTE long singles as a proxy for futures strategies — "an option single is a futures contract on its last day"
- [Trapped-Seller Fuel](trapped-seller-fuel.md) — The 08-19 Carmine insight as a measurable entry feature: underwater aggression at the level, lid rejections, absorbed dips, thin above — measured quantities only, never the cohorts-and-stops narrative
- [V-Day Target Is v_down Only](v-day-target-is-v-down-only.md) — For st-r2o V-day detection, Steve's actual butterfly-strategy target is v_down only; v_up (inverted-V) is diagnostic, not a trade setup

### reference

- [Carmine Rosato — InvestiTrade LVN Method](carmine-rosato-investitrade-lvn-method.md) — Carmine Rosato / InvestiTrade — order-flow + supply/demand "Low Volume Node" method Steve models; LVN = zone left by a fast departure
- [SPXW Final-Fifteen Strike Concentration](spxw-final-fifteen-strike-concentration.md) — Measured 08-30: the 32 strikes within ±40 pts of ES carry ~3/4 of SPXW print volume in the last fifteen minutes while quotes spread across the whole surface — narrowing is a quote-schema lever, not a trades lever
- [Zone Framework Equivalence](zone-framework-equivalence.md) — Supply/Demand (Seiden), ICT, SMC, and Carmine's LVN are one event in four dialects — a fast departure leaving unfilled orders + trapped traders

### rule

- [Channel Family Taxonomy](channel-family-taxonomy.md) — The ten channel families a study design must traverse before measuring, with a written verdict per family — a family with no entry is a finding, not a silence
- [Never Guess Chart Readings](never-guess-chart-readings.md) — MANDATORY procedure for reading chart screenshots — crop regions at full resolution before quoting any number

### runbook

- [Schwab Auth Pattern](schwab-auth-pattern.md) — Token-file auth through the hobbled-readonly schwab-py fork (submodule, editable) behind the gate key; seven-day refresh token renewed by Steve with the refresh script and its two-check grant validation; callback URL has no trailing slash (rewritten 2026-09-05)
