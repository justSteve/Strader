# Market Entity Model — Design Spec

**Bead:** co-movy
**Date:** 2026-05-17
**Status:** Draft — awaiting review
**Authors:** COO (structural lead), Strader (domain validation), Steve (direction)

## Problem

Strader's codebase is a collection of standalone tools with no shared entity layer. The Schwab client returns raw JSON. The chain reader prints formatted text. The Mancini parser produces its own dataclasses. Nothing composes. Every new indicator or tool re-parses the same data, re-navigates the same JSON paths, and re-invents the same normalizations.

This spec defines the foundational data model that all of Strader's trading tooling builds on.

## Global Conventions

- **Timezone: US/Central throughout.** All `datetime` values are timezone-aware, US/Central. No UTC normalization, no Eastern. `ingest.py` converts at the boundary; everything inside `market/` is already Central.

## Design Principles

1. **Strader's primary product is code, not real-time inference.** The entity model backs a library of coded indicators and decision rules that operate deterministically. Steve takes this code into the trading room. It works without Strader present.
2. **Instrument-centric.** The core entity is the instrument. Sessions, strategies, and signals are lenses applied to instruments.
3. **Template + instance.** Abstract strategy definitions (templates) resolve against live market data into concrete contract instances. Mirrors the ECC pattern: declarative definition that materializes into working state.
4. **Pure functions for indicators.** Market data in, typed signal out. No side effects, no agent in the hot path. Composable, backtestable by construction.
5. **Explicit escape hatch.** When pattern recognition isn't yet codeable, an indicator returns a typed `InferenceRequest` instead of guessing. This shrinks over time as inference gets converted to deterministic rules.

## Division of Labor

- **COO** drives structural decisions: entity relationships, module boundaries, composition patterns. Has authority from the ECC/zgent/zepo entity modeling track record.
- **Strader** validates domain fit: do these entities reflect how the market actually works? Are the indicator signatures capturing the right inputs?
- **Steve** directs vision, validates results, provides domain context that neither agent has.

COO is primary driver for initial development sessions. Strader graduates to self-driving once the framework patterns are established.

## Entity Layer

All entities are immutable dataclasses. No ORM, no persistence layer. Constructed fresh from market data on each evaluation cycle.

### Core Types

```
Instrument          (base: symbol, asset_type)
+-- Index           (SPX, /ES -- cash-settled, has chain)
+-- Contract        (single option: strike, expiry, put/call, greeks)
+-- Spread          (template + resolved instances)
    +-- Butterfly   (center, width -> 3 legs)
    +-- Vertical    (2 legs)
    +-- Single      (1 leg, trivial spread)

Chain               (all contracts for a symbol+expiry, indexed by strike)
Session             (trading day: date, regime, OHLC, levels, GEX posture)
Position            (held spread: entry_price, quantity, current_value, greeks)
```

### Contract — The Atom

Everything composes from contracts. A `Contract` represents a single option:

```python
@dataclass(frozen=True)
class Contract:
    symbol: str           # e.g. "SPXW260517C05800"
    underlying: str       # e.g. "$SPX"
    strike: float
    expiry: date
    contract_type: Literal["CALL", "PUT"]
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float
```

### Spread — Template and Instance

A `SpreadTemplate` is an abstract definition:

```python
@dataclass(frozen=True)
class ButterflyTemplate:
    center: str              # "ATM", "ATM+5", or absolute strike
    width: int               # distance between legs
    expiry: str              # "0DTE", "1DTE", or ISO date
    contract_type: Literal["CALL", "PUT"]
```

A `SpreadInstance` is resolved against a live chain:

```python
@dataclass(frozen=True)
class ButterflyInstance:
    template: ButterflyTemplate
    lower: Contract
    center: Contract          # 2x quantity
    upper: Contract
    net_debit: float          # cost to enter
    max_profit: float         # at expiry if pinned at center
    max_loss: float           # net debit paid
    breakeven_lower: float
    breakeven_upper: float
```

Resolution is an explicit step in `market/resolve.py`: template + chain -> instance (or error if strikes unavailable).

### Chain — The Lookup Table

Normalizes the Schwab chain API response into an indexed structure:

```python
@dataclass(frozen=True)
class Chain:
    underlying: str
    expiry: date
    calls: dict[float, Contract]    # strike -> Contract
    puts: dict[float, Contract]     # strike -> Contract
    underlying_price: float
```

Supports lookups: `chain.call(5800)`, `chain.nearest_call(atm_price)`, `chain.range(5780, 5820, "CALL")`.

### Session — Day Context

Carries the regime and level context that indicators depend on:

```python
@dataclass(frozen=True)
class Session:
    date: date
    underlying_price: float
    open: float
    high: float
    low: float
    gex_posture: Literal["positive", "negative", "neutral"]
    vix: float
    mancini_supports: list[Level]
    mancini_resistances: list[Level]
    regime: Regime | None         # set by regime indicator
    opening_range: tuple[float, float] | None
```

Session is the bridge between Mancini email parsing (which produces levels) and indicator evaluation (which consumes them). `market/ingest.py` handles both paths.

## Signal Types

Every indicator produces a typed signal. Signals are the currency of the system.

```
Signal (base)
+-- Bias        direction + confidence: bullish/bearish/neutral, 0.0-1.0
+-- Level       price + annotation: support/resistance/target/stop
+-- Alert       severity + message: triggered when conditions met
+-- Action      verb + params: "enter butterfly at 5800, width 5"
+-- Regime      market state: trending/ranging/volatile/compressed
```

Common fields on all signals:

```python
@dataclass(frozen=True)
class Signal:
    timestamp: datetime      # timezone-aware, US/Central
    source: str              # indicator name that produced this
    confidence: float        # 0.0 to 1.0
    reason: str              # one-line human-readable explanation
```

**Actions are recommendations, not executions.** An `Action` signal means conditions are met for a trade. It still requires Steve's confirmation before touching the Schwab API. The gate key boundary is never bypassed.

## Indicator Layer

### Registration and Composition

Each indicator is a decorated pure function:

```python
@indicator(
    inputs=[Chain, Session],
    output=Bias,
    name="gex_regime"
)
def gex_regime(chain: Chain, session: Session) -> Bias:
    ...
```

The `@indicator` decorator registers:
- **Input types** — what entities or signals this indicator consumes
- **Output type** — what signal it produces
- **Name** — unique identifier for dependency resolution

The registry auto-resolves execution order from the dependency graph. If indicator B declares indicator A's output type as an input, A runs first and B receives its result.

### Inference Escape Hatch

When an indicator can't yet produce a deterministic answer:

```python
@indicator(
    inputs=[Chain, Session, FootprintSnapshot],
    output=Bias,
    name="footprint_context",
    requires_inference=True
)
def footprint_context(chain, session, footprint) -> Bias | InferenceRequest:
    if footprint.absorption_ratio > 3.0:
        return Bias("bearish", confidence=0.8, reason="strong absorption at highs")
    return InferenceRequest(
        context=footprint,
        question="Is this accumulation or distribution?",
        output_type=Bias
    )
```

`InferenceRequest` is explicit and typed — it declares what context goes to the agent and what signal type comes back. Over time, patterns in inference responses become deterministic rules. The escape hatch shrinks.

### Initial Indicators (POC scope)

| Indicator | Inputs | Output | Strategy |
|-----------|--------|--------|----------|
| `gex_regime` | Chain, Session | Regime | All |
| `mancini_levels` | Session | Level[] | All |
| `butterfly_entry` | Chain, Session, Regime | Action | Late-day butterflies |
| `orb_breakout` | Session | Action | Opening range breakout |
| `scalp_pivot` | Chain, Session, Level[] | Action | Range scalping |
| `position_risk` | Position[], Session | Alert | Risk management |

## Module Structure

```
Strader/
+-- market/                     # Pure Python library — zero external deps
|   +-- entities/
|   |   +-- instrument.py       # Instrument, Index, Contract
|   |   +-- spread.py           # SpreadTemplate, SpreadInstance, Butterfly, Vertical
|   |   +-- chain.py            # Chain (indexed contract lookup)
|   |   +-- session.py          # Session (day context, regime, levels)
|   |   +-- position.py         # Position (held spread + live P&L)
|   |
|   +-- signals/
|   |   +-- types.py            # Signal, Bias, Level, Alert, Action, Regime
|   |
|   +-- indicators/
|   |   +-- registry.py         # @indicator decorator, dependency resolution
|   |   +-- gex.py              # GEX regime, dealer positioning
|   |   +-- levels.py           # Support/resistance from Mancini + LuxAlgo
|   |   +-- butterfly.py        # Butterfly entry conditions
|   |   +-- orb.py              # Opening range breakout detection
|   |   +-- scalp.py            # Range scalp pivot evaluation
|   |
|   +-- resolve.py              # Template -> instance resolution
|   +-- ingest.py               # Schwab JSON / Mancini parse -> entities
|   +-- inference.py            # InferenceRequest handling
|
+-- present/                    # tmux rendering — separate from logic
|   +-- positions.py            # Position pane formatter
|   +-- signals.py              # Signal feed pane formatter
|   +-- regime.py               # Regime/session context pane
|   +-- alerts.py               # Alert pane formatter
|
+-- schwab/                     # Existing — thin API client
+-- mancini/                    # Existing — email parser, feeds Session.levels
+-- tools/                      # Existing — tv_capture (Windows-side)
+-- daemon/                     # Existing — session scripts
```

### Boundaries

- `market/` has zero dependencies on schwab client, tmux, or agent runtime. Fully testable in isolation.
- `present/` depends on `market/` signals but never on `schwab/` or agent internals.
- Existing code stays put. `market/ingest.py` bridges raw API output and parsed emails into typed entities.
- One indicator per file. Files stay small enough for a polecat to hold in context.

## Data Flow

```
Schwab API --> schwab/client.py --> raw JSON
                                       |
                                       v
                             market/ingest.py
                             (normalize to entities)
                                       |
                                       v
                             Chain, Session, Contract
                                       |
                         +-------------+-------------+
                         v             v             v
                   gex.py         levels.py    butterfly.py
                  (Regime)        (Level[])      (Action)
                         |             |             |
                         +-------------+-------------+
                                       v
                             Signal[] (typed outputs)
                                       |
                         +-------------+-------------+
                         v             v             v
                  present/       Strader agent    backtest
                  (tmux panes)   (inference       (historical
                                  escape hatch)    replay)
```

Three consumers of the same signal stream: tmux panes for Steve, agent inference for edge cases, backtesting for validation.

## What's NOT in the POC

Deliberately excluded from the first pass:

- **No persistence layer.** Entities are ephemeral, constructed per evaluation cycle. If we learn we need history, that's an informed decision.
- **No event sourcing.** If we learn we need replay semantics, that's the informed over-engineering step.
- **No real-time streaming.** Poll-based for now. Schwab API is polling anyway.
- **No multi-day backtest harness.** Single-session evaluation first.
- **No LuxAlgo integration.** Separate ingest path to add once the entity layer proves out.

These are not rejected — they're deferred until real usage tells us which ones earn their complexity.

## tmux Presentation

The `present/` layer formats signal outputs for Strader's tmux panes:

| Pane | Content | Source signals |
|------|---------|---------------|
| Regime | Current market state, GEX posture, VIX | Regime, Bias |
| Levels | Support/resistance table with annotations | Level[] |
| Signals | Live signal feed with confidence and reason | All signals |
| Positions | Held positions with live P&L and Greeks | Position[] |
| Alerts | Triggered alerts by severity | Alert[] |

Each presenter is a function that takes signals and returns formatted text for a tmux pane. No tmux coupling in the presenter itself — a thin driver script calls the presenter and sends output to the pane via `tmux send-keys`.

## Testing Strategy

- **Entity construction:** Unit tests that build entities from fixture JSON and verify normalization.
- **Indicator logic:** Unit tests with synthetic entities — no API calls, no mocks needed. Feed known inputs, assert expected signal outputs.
- **Resolution:** Unit tests for template -> instance resolution against fixture chains.
- **Integration:** End-to-end from fixture JSON through ingest -> indicators -> signals. Verify the full pipeline produces expected outputs for known market scenarios.
- **Backtest compatibility:** Any test fixture can serve double duty as a backtest scenario. The same indicator code runs against historical and live data.

## Implementation Sequence

1. **Entity layer** — `market/entities/` with all core types and `market/ingest.py` for Schwab normalization
2. **Signal types** — `market/signals/types.py`
3. **Indicator registry** — `market/indicators/registry.py` with `@indicator` decorator and dependency resolution
4. **First indicator** — `gex_regime` as proof that the full path works (ingest -> entity -> indicator -> signal)
5. **Resolution** — `market/resolve.py` for template -> instance (butterfly focus)
6. **Presenters** — `present/` layer, starting with regime and signals panes
7. **Remaining indicators** — build out per strategy needs
