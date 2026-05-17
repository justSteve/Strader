# Market Entity Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational typed entity and indicator layer for Strader's trading tooling, replacing ad-hoc raw JSON navigation with composable, testable, backtestable Python code.

**Bead:** co-movy

**Architecture:** All market entities are immutable frozen dataclasses in `market/`, which has zero external dependencies beyond stdlib and is fully testable without the Schwab API or tmux. `market/ingest.py` is the sole bridge between the existing codebase and the entity layer — it imports from `mancini/` and `schwab/` and converts to typed entities, performing US/Central timezone normalization at the boundary. An `@indicator` decorator registers indicators in an ordered list; execution order is registration order for the POC (dependency auto-resolver deferred).

**Tech Stack:** Python 3.12, `dataclasses` (stdlib), `zoneinfo` (stdlib), `pytest`. No new pip installs required.

---

## Prerequisites

```bash
cd /root/projects/Strader
source .venv/bin/activate
python --version   # 3.12.x
python -m pytest --version
```

---

## File Map

**New files (all of `market/`, `present/`, `tests/`):**

```
market/
├── __init__.py
├── entities/
│   ├── __init__.py
│   ├── level.py          # Level(price, label, source, annotation)
│   ├── instrument.py     # Instrument (base), Index, Contract
│   ├── chain.py          # Chain — int-keyed strike lookup + helpers
│   ├── session.py        # Session — raw day context (NO regime, NO opening_range)
│   ├── spread.py         # ButterflyTemplate, ButterflyInstance
│   └── position.py       # Position
├── signals/
│   ├── __init__.py
│   └── types.py          # Signal, Bias, Level (signal), Alert, Action, Regime, InferenceRequest
├── indicators/
│   ├── __init__.py
│   ├── registry.py       # @indicator decorator, ordered _REGISTRY list, run_indicators()
│   └── gex.py            # gex_regime indicator
├── resolve.py            # resolve_butterfly(template, chain) -> ButterflyInstance
└── ingest.py             # chain_from_schwab(), session_from_mancini() — boundary layer, TZ conversion here

present/
├── __init__.py
├── regime.py             # format_regime(regime, session) -> str
├── signals.py            # format_signals(signals) -> str
└── driver.sh             # tmux pane updater (load-buffer + paste-buffer)

tests/
├── __init__.py
├── conftest.py
└── market/
    ├── __init__.py
    ├── fixtures/
    │   └── schwab_chain_spx.json
    ├── entities/
    │   ├── __init__.py
    │   ├── test_level.py
    │   ├── test_instrument.py
    │   ├── test_chain.py
    │   ├── test_session.py
    │   ├── test_spread.py
    │   └── test_position.py
    ├── signals/
    │   ├── __init__.py
    │   └── test_types.py
    ├── indicators/
    │   ├── __init__.py
    │   ├── test_registry.py
    │   └── test_gex.py
    ├── present/
    │   ├── __init__.py
    │   ├── test_regime.py
    │   └── test_signals.py
    ├── test_ingest.py
    ├── test_ingest_session.py
    └── test_resolve.py
```

**Existing files untouched:** `schwab/`, `mancini/`, `daemon/`, `tools/`. The new `market/` module bridges these via `ingest.py` only.

---

## Task 1: Package scaffolding and signal types

**Why first:** Signal types are imported by every other module. Zero dependencies. Getting them right before entity code prevents type churn across the rest of the plan.

**Files:**
- Create: `market/__init__.py`, `market/entities/__init__.py`, `market/signals/__init__.py`, `market/indicators/__init__.py`
- Create: `market/signals/types.py`
- Create: `tests/__init__.py`, `tests/market/__init__.py`, `tests/market/signals/__init__.py`, `tests/market/signals/test_types.py`

- [ ] **Step 1: Write failing tests**

Create `tests/market/signals/test_types.py`:

```python
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from market.signals.types import Signal, Bias, Regime, Alert, Action, InferenceRequest

CENTRAL = ZoneInfo("America/Chicago")

def _ts():
    return datetime(2026, 5, 17, 9, 30, tzinfo=CENTRAL)

def test_bias_is_signal():
    b = Bias(timestamp=_ts(), source="gex_regime", confidence=0.8, reason="GEX negative", direction="bearish")
    assert isinstance(b, Signal)
    assert b.direction == "bearish"
    assert b.confidence == 0.8

def test_regime_is_signal():
    r = Regime(timestamp=_ts(), source="gex_regime", confidence=0.7, reason="compressed", state="compressed")
    assert isinstance(r, Signal)
    assert r.state == "compressed"

def test_alert_is_signal():
    a = Alert(timestamp=_ts(), source="position_risk", confidence=1.0, reason="delta exceeded", severity="warn", message="delta limit")
    assert a.severity == "warn"

def test_action_is_signal():
    act = Action(
        timestamp=_ts(), source="butterfly_entry", confidence=0.9, reason="conditions met",
        verb="enter_butterfly", params={"strike": 5800, "width": 5},
    )
    assert act.verb == "enter_butterfly"
    assert act.params["strike"] == 5800

def test_inference_request():
    req = InferenceRequest(
        timestamp=_ts(), source="footprint_context", confidence=0.0, reason="pattern unclear",
        context={"absorption_ratio": 2.5},
        question="Is this accumulation or distribution?",
        output_type="Bias",
    )
    assert req.output_type == "Bias"

def test_signal_timestamp_is_central():
    b = Bias(timestamp=_ts(), source="test", confidence=1.0, reason="test", direction="neutral")
    assert b.timestamp.tzinfo == CENTRAL

def test_dataclasses_are_frozen():
    b = Bias(timestamp=_ts(), source="test", confidence=1.0, reason="test", direction="neutral")
    with pytest.raises((AttributeError, TypeError)):
        b.direction = "bullish"  # type: ignore
```

- [ ] **Step 2: Run — expect import failure**

```bash
cd /root/projects/Strader && source .venv/bin/activate
python -m pytest tests/market/signals/test_types.py -v
```
Expected: `ModuleNotFoundError: No module named 'market'`

- [ ] **Step 3: Create package init files**

```bash
mkdir -p market/entities market/signals market/indicators
touch market/__init__.py market/entities/__init__.py market/signals/__init__.py market/indicators/__init__.py
mkdir -p tests/market/entities tests/market/signals tests/market/indicators tests/market/fixtures tests/market/present
touch tests/__init__.py tests/market/__init__.py
touch tests/market/entities/__init__.py tests/market/signals/__init__.py
touch tests/market/indicators/__init__.py tests/market/present/__init__.py
```

- [ ] **Step 4: Create `market/signals/types.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class Signal:
    timestamp: datetime  # timezone-aware, US/Central throughout
    source: str          # indicator name that produced this
    confidence: float    # 0.0 to 1.0
    reason: str          # one-line human-readable explanation


@dataclass(frozen=True)
class Bias(Signal):
    direction: Literal["bullish", "bearish", "neutral"] = "neutral"


@dataclass(frozen=True)
class Regime(Signal):
    state: Literal["trending", "ranging", "volatile", "compressed"] = "ranging"


@dataclass(frozen=True)
class Level(Signal):
    price: float = 0.0
    level_type: Literal["support", "resistance", "target", "stop"] = "support"


@dataclass(frozen=True)
class Alert(Signal):
    severity: Literal["info", "warn", "critical"] = "info"
    message: str = ""


@dataclass(frozen=True)
class Action(Signal):
    # Actions are recommendations, not executions. Steve confirms before
    # anything touches the Schwab API. The gate key boundary is never bypassed.
    verb: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceRequest(Signal):
    # Escape hatch for patterns not yet codeable deterministically.
    # FootprintSnapshot (mentioned in spec examples) is illustrative —
    # no such type is defined here. When that indicator is built, its
    # context type will be defined in that task.
    context: Any = None
    question: str = ""
    output_type: str = ""  # name of the expected Signal subclass
```

- [ ] **Step 5: Run — expect PASS**

```bash
python -m pytest tests/market/signals/test_types.py -v
```
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add market/ tests/__init__.py tests/market/
git commit -m "feat: market package scaffold and signal types [co-movy]"
```

---

## Task 2: Level entity

**Files:**
- Create: `market/entities/level.py`
- Create: `tests/market/entities/test_level.py`

`mancini/parser.py` already defines a `Level(price, annotation)`. That is a different type — the mancini parser's internal representation. The entity model's `Level` adds a `source` field so consumers know provenance. `market/ingest.py` (Task 9) bridges the two. This keeps `market/` independent of `mancini/`.

- [ ] **Step 1: Write failing test**

Create `tests/market/entities/test_level.py`:

```python
import pytest
from market.entities.level import Level

def test_level_construction():
    lev = Level(price=5780.0, label="support", source="mancini")
    assert lev.price == 5780.0
    assert lev.label == "support"
    assert lev.source == "mancini"

def test_level_is_frozen():
    lev = Level(price=5780.0, label="support", source="mancini")
    with pytest.raises((AttributeError, TypeError)):
        lev.price = 5790.0  # type: ignore

def test_level_with_annotation():
    lev = Level(price=5800.0, label="resistance", source="mancini", annotation="major")
    assert lev.annotation == "major"

def test_level_default_annotation():
    lev = Level(price=5800.0, label="resistance", source="mancini")
    assert lev.annotation == ""
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/entities/test_level.py -v
```
Expected: `ModuleNotFoundError: No module named 'market.entities.level'`

- [ ] **Step 3: Create `market/entities/level.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Level:
    price: float
    label: Literal["support", "resistance", "target", "stop"]
    source: str           # "mancini", "manual", "luxalgo"
    annotation: str = ""  # "major", "minor", or empty
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/entities/test_level.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add market/entities/level.py tests/market/entities/
git commit -m "feat: Level entity [co-movy]"
```

---

## Task 3: Session entity

**Files:**
- Create: `market/entities/session.py`
- Create: `tests/market/entities/test_session.py`

**Critical:** `Session` carries raw context at session start. It does NOT have `regime` or `opening_range` fields. `regime` is produced by `gex_regime`; `opening_range` is produced by `orb_breakout`. Indicators that need these receive them as explicit parameters. This eliminates the circular dependency where an indicator's input type carries the indicator's own output.

- [ ] **Step 1: Write failing test**

Create `tests/market/entities/test_session.py`:

```python
import dataclasses
import pytest
from datetime import date
from market.entities.session import Session
from market.entities.level import Level

def _supports():
    return (
        Level(price=5780.0, label="support", source="mancini"),
        Level(price=5750.0, label="support", source="mancini", annotation="major"),
    )

def test_session_construction():
    s = Session(
        date=date(2026, 5, 17),
        underlying_price=5820.5,
        open=5800.0,
        high=5840.0,
        low=5795.0,
        gex_posture="negative",
        vix=14.8,
        mancini_supports=_supports(),
        mancini_resistances=(Level(price=5850.0, label="resistance", source="mancini"),),
    )
    assert s.underlying_price == 5820.5
    assert s.gex_posture == "negative"
    assert len(s.mancini_supports) == 2

def test_session_is_frozen():
    s = Session(
        date=date(2026, 5, 17), underlying_price=5820.5, open=5800.0,
        high=5840.0, low=5795.0, gex_posture="negative", vix=14.8,
        mancini_supports=(), mancini_resistances=(),
    )
    with pytest.raises((AttributeError, TypeError)):
        s.underlying_price = 5830.0  # type: ignore

def test_session_has_no_regime_or_opening_range():
    field_names = {f.name for f in dataclasses.fields(Session)}
    assert "regime" not in field_names, "Session must not carry regime — produced by indicator"
    assert "opening_range" not in field_names, "Session must not carry opening_range — produced by orb indicator"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/entities/test_session.py -v
```

- [ ] **Step 3: Create `market/entities/session.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal

from market.entities.level import Level


@dataclass(frozen=True)
class Session:
    date: date
    underlying_price: float
    open: float
    high: float
    low: float
    gex_posture: Literal["positive", "negative", "neutral"]
    vix: float
    mancini_supports: tuple[Level, ...]      # use tuple not list: frozen dataclass requires hashable fields
    mancini_resistances: tuple[Level, ...]
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/entities/test_session.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add market/entities/session.py tests/market/entities/test_session.py
git commit -m "feat: Session entity — raw context, no regime or opening_range [co-movy]"
```

---

## Task 4: Contract and Chain entities

**Files:**
- Create: `market/entities/instrument.py`
- Create: `market/entities/chain.py`
- Create: `tests/market/entities/test_instrument.py`
- Create: `tests/market/entities/test_chain.py`

**Strike key design:** `Chain` stores contracts keyed by `int`, not `float`. Key = `round(strike * 10)`. So 5800.0 → 58000, 5800.5 → 58005. `chain.call(5800.0)` and `chain.put(5800.0)` do the conversion internally — callers use float strikes naturally.

- [ ] **Step 1: Write failing tests**

Create `tests/market/entities/test_instrument.py`:

```python
import pytest
from datetime import date
from market.entities.instrument import Contract

def _contract(**kwargs):
    defaults = dict(
        symbol="SPXW  260517C05800000", underlying="$SPX",
        strike=5800.0, expiry=date(2026, 5, 17), contract_type="CALL",
        bid=22.5, ask=23.0, last=22.7,
        volume=1523, open_interest=4521,
        delta=0.42, gamma=0.012, theta=-8.5, vega=2.1, implied_volatility=14.8,
    )
    defaults.update(kwargs)
    return Contract(**defaults)

def test_contract_construction():
    c = _contract()
    assert c.strike == 5800.0
    assert c.contract_type == "CALL"
    assert c.delta == 0.42

def test_contract_is_frozen():
    c = _contract()
    with pytest.raises((AttributeError, TypeError)):
        c.bid = 25.0  # type: ignore

def test_contract_mid():
    c = _contract(bid=22.0, ask=24.0)
    assert c.mid == 23.0
```

Create `tests/market/entities/test_chain.py`:

```python
import pytest
from datetime import date
from market.entities.instrument import Contract
from market.entities.chain import Chain, strike_key

def _contract(strike: float, side: str) -> Contract:
    return Contract(
        symbol=f"SPXW260517{'C' if side == 'CALL' else 'P'}{int(strike * 10):08d}",
        underlying="$SPX", strike=strike, expiry=date(2026, 5, 17),
        contract_type=side,
        bid=10.0, ask=10.5, last=10.2, volume=100, open_interest=500,
        delta=0.3 if side == "CALL" else -0.3,
        gamma=0.01, theta=-5.0, vega=1.5, implied_volatility=14.0,
    )

def _chain():
    strikes = [5780.0, 5790.0, 5800.0, 5810.0, 5820.0]
    calls = {strike_key(s): _contract(s, "CALL") for s in strikes}
    puts  = {strike_key(s): _contract(s, "PUT")  for s in strikes}
    return Chain(
        underlying="$SPX", expiry=date(2026, 5, 17),
        calls=calls, puts=puts, underlying_price=5802.5,
    )

def test_strike_key_whole():
    assert strike_key(5800.0) == 58000

def test_strike_key_half():
    assert strike_key(5800.5) == 58005

def test_chain_call_lookup():
    c = _chain().call(5800.0)
    assert c.strike == 5800.0
    assert c.contract_type == "CALL"

def test_chain_put_lookup():
    p = _chain().put(5800.0)
    assert p.contract_type == "PUT"

def test_chain_missing_strike_raises():
    with pytest.raises(KeyError):
        _chain().call(9999.0)

def test_chain_nearest_call():
    c = _chain().nearest_call(5803.0)
    assert c.strike in (5800.0, 5810.0)

def test_chain_range():
    contracts = _chain().range(5790.0, 5810.0, "CALL")
    strikes = {c.strike for c in contracts}
    assert {5790.0, 5800.0, 5810.0} == strikes
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/entities/test_instrument.py tests/market/entities/test_chain.py -v
```

- [ ] **Step 3: Create `market/entities/instrument.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class Instrument:
    symbol: str
    underlying: str


@dataclass(frozen=True)
class Index(Instrument):
    pass


@dataclass(frozen=True)
class Contract(Instrument):
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

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2
```

- [ ] **Step 4: Create `market/entities/chain.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal

from market.entities.instrument import Contract


def strike_key(price: float) -> int:
    """Convert strike price to collision-safe int key. 5800.5 -> 58005."""
    return round(price * 10)


@dataclass(frozen=True)
class Chain:
    underlying: str
    expiry: date
    calls: dict[int, Contract]   # strike_key(strike) -> Contract
    puts: dict[int, Contract]
    underlying_price: float

    def call(self, strike: float) -> Contract:
        return self.calls[strike_key(strike)]

    def put(self, strike: float) -> Contract:
        return self.puts[strike_key(strike)]

    def nearest_call(self, price: float) -> Contract:
        key = min(self.calls.keys(), key=lambda k: abs(k - strike_key(price)))
        return self.calls[key]

    def nearest_put(self, price: float) -> Contract:
        key = min(self.puts.keys(), key=lambda k: abs(k - strike_key(price)))
        return self.puts[key]

    def range(self, low: float, high: float, side: Literal["CALL", "PUT"]) -> list[Contract]:
        source = self.calls if side == "CALL" else self.puts
        lo, hi = strike_key(low), strike_key(high)
        return [c for k, c in sorted(source.items()) if lo <= k <= hi]
```

- [ ] **Step 5: Run — expect PASS**

```bash
python -m pytest tests/market/entities/test_instrument.py tests/market/entities/test_chain.py -v
```
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add market/entities/instrument.py market/entities/chain.py \
    tests/market/entities/test_instrument.py tests/market/entities/test_chain.py
git commit -m "feat: Contract and Chain entities with int strike keys [co-movy]"
```

---

## Task 5: Spread entities

**Files:**
- Create: `market/entities/spread.py`
- Create: `tests/market/entities/test_spread.py`

- [ ] **Step 1: Write failing tests**

Create `tests/market/entities/test_spread.py`:

```python
import pytest
from datetime import date
from market.entities.instrument import Contract
from market.entities.spread import ButterflyTemplate, ButterflyInstance

def _contract(strike: float) -> Contract:
    return Contract(
        symbol=f"SPXW260517C{int(strike)}000", underlying="$SPX",
        strike=strike, expiry=date(2026, 5, 17), contract_type="CALL",
        bid=10.0, ask=10.5, last=10.2, volume=100, open_interest=500,
        delta=0.3, gamma=0.01, theta=-5.0, vega=1.5, implied_volatility=14.0,
    )

def _instance() -> ButterflyInstance:
    return ButterflyInstance(
        template=ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL"),
        lower=_contract(5790.0),
        center=_contract(5800.0),
        upper=_contract(5810.0),
        net_debit=2.5, max_profit=7.5, max_loss=2.5,
        breakeven_lower=5792.5, breakeven_upper=5807.5,
    )

def test_butterfly_template():
    t = ButterflyTemplate(center="ATM", width=5, expiry="0DTE", contract_type="CALL")
    assert t.center == "ATM"
    assert t.width == 5

def test_butterfly_template_is_frozen():
    t = ButterflyTemplate(center="ATM", width=5, expiry="0DTE", contract_type="CALL")
    with pytest.raises((AttributeError, TypeError)):
        t.width = 10  # type: ignore

def test_butterfly_instance():
    inst = _instance()
    assert inst.net_debit == 2.5
    assert inst.max_profit == 7.5
    assert inst.center.strike == 5800.0

def test_butterfly_instance_is_frozen():
    inst = _instance()
    with pytest.raises((AttributeError, TypeError)):
        inst.net_debit = 3.0  # type: ignore
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/entities/test_spread.py -v
```

- [ ] **Step 3: Create `market/entities/spread.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from market.entities.instrument import Contract


@dataclass(frozen=True)
class ButterflyTemplate:
    center: str                           # "ATM", "ATM+5", "ATM-5", or absolute strike as string
    width: int                            # distance in points between legs
    expiry: str                           # "0DTE", "1DTE", or ISO date string
    contract_type: Literal["CALL", "PUT"]


@dataclass(frozen=True)
class ButterflyInstance:
    template: ButterflyTemplate
    lower: Contract
    center: Contract    # held at 2x quantity
    upper: Contract
    net_debit: float    # cost to enter (positive = debit paid)
    max_profit: float   # at expiry if pinned at center strike
    max_loss: float     # equals net_debit
    breakeven_lower: float
    breakeven_upper: float
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/entities/test_spread.py -v
```

- [ ] **Step 5: Commit**

```bash
git add market/entities/spread.py tests/market/entities/test_spread.py
git commit -m "feat: ButterflyTemplate and ButterflyInstance entities [co-movy]"
```

---

## Task 6: Position entity

**Files:**
- Create: `market/entities/position.py`
- Create: `tests/market/entities/test_position.py`

- [ ] **Step 1: Write failing tests**

Create `tests/market/entities/test_position.py`:

```python
import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from market.entities.instrument import Contract
from market.entities.spread import ButterflyTemplate, ButterflyInstance
from market.entities.position import Position

CENTRAL = ZoneInfo("America/Chicago")

def _contract(strike: float) -> Contract:
    return Contract(
        symbol=f"SPXW260517C{int(strike)}000", underlying="$SPX",
        strike=strike, expiry=date(2026, 5, 17), contract_type="CALL",
        bid=10.0, ask=10.5, last=10.2, volume=100, open_interest=500,
        delta=0.3, gamma=0.01, theta=-5.0, vega=1.5, implied_volatility=14.0,
    )

def _instance() -> ButterflyInstance:
    return ButterflyInstance(
        template=ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL"),
        lower=_contract(5790.0), center=_contract(5800.0), upper=_contract(5810.0),
        net_debit=2.5, max_profit=7.5, max_loss=2.5,
        breakeven_lower=5792.5, breakeven_upper=5807.5,
    )

def test_position_construction():
    p = Position(
        spread=_instance(), entry_price=2.5, quantity=1,
        entry_time=datetime(2026, 5, 17, 14, 30, tzinfo=CENTRAL),
        current_value=3.0, net_delta=0.05, net_gamma=0.002,
        net_theta=-2.5, net_vega=0.8,
    )
    assert p.entry_price == 2.5
    assert p.quantity == 1

def test_position_unrealized_pnl():
    p = Position(
        spread=_instance(), entry_price=2.5, quantity=1,
        entry_time=datetime(2026, 5, 17, 14, 30, tzinfo=CENTRAL),
        current_value=3.0, net_delta=0.05, net_gamma=0.002,
        net_theta=-2.5, net_vega=0.8,
    )
    assert p.unrealized_pnl == 50.0  # (3.0 - 2.5) * 1 * 100

def test_position_is_frozen():
    p = Position(
        spread=_instance(), entry_price=2.5, quantity=1,
        entry_time=datetime(2026, 5, 17, 14, 30, tzinfo=CENTRAL),
        current_value=3.0, net_delta=0.05, net_gamma=0.002,
        net_theta=-2.5, net_vega=0.8,
    )
    with pytest.raises((AttributeError, TypeError)):
        p.current_value = 4.0  # type: ignore
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/entities/test_position.py -v
```

- [ ] **Step 3: Create `market/entities/position.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from market.entities.spread import ButterflyInstance


@dataclass(frozen=True)
class Position:
    spread: ButterflyInstance
    entry_price: float
    quantity: int
    entry_time: datetime    # timezone-aware, US/Central
    current_value: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_value - self.entry_price) * self.quantity * 100
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/entities/test_position.py -v
```

- [ ] **Step 5: Commit**

```bash
git add market/entities/position.py tests/market/entities/test_position.py
git commit -m "feat: Position entity [co-movy]"
```

---

## Task 7: Indicator registry

**Files:**
- Create: `market/indicators/registry.py`
- Create: `tests/market/indicators/test_registry.py`

**Design note:** Auto-resolving execution order from type annotations is deferred. `_REGISTRY` is an ordered list; indicators run in registration order. Metadata (`inputs`, `output`) is still collected via the decorator — it's the data structure for the future dependency resolver. This is noted in the code.

- [ ] **Step 1: Write failing tests**

Create `tests/market/indicators/test_registry.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo
from market.entities.session import Session
from market.signals.types import Signal, Bias, Regime
from market.indicators.registry import indicator, run_indicators, _REGISTRY

CENTRAL = ZoneInfo("America/Chicago")

def _session() -> Session:
    return Session(
        date=date(2026, 5, 17), underlying_price=5820.5,
        open=5800.0, high=5840.0, low=5795.0,
        gex_posture="negative", vix=14.8,
        mancini_supports=(), mancini_resistances=(),
    )

def _ts():
    return datetime(2026, 5, 17, 9, 30, tzinfo=CENTRAL)

def test_indicator_registers():
    initial = len(_REGISTRY)

    @indicator(inputs=["Chain", "Session"], output="Bias", name="test_reg_bias")
    def _f(chain, session) -> Bias:
        return Bias(timestamp=_ts(), source="test_reg_bias", confidence=0.8, reason="test", direction="bullish")

    assert len(_REGISTRY) == initial + 1
    assert _REGISTRY[-1].name == "test_reg_bias"

def test_run_indicators_returns_signals():
    @indicator(inputs=["Session"], output="Regime", name="test_reg_regime")
    def _f(chain, session) -> Regime:
        return Regime(timestamp=_ts(), source="test_reg_regime", confidence=0.7, reason="test", state="ranging")

    signals = run_indicators(chain=None, session=_session())
    assert any(isinstance(s, Regime) for s in signals)

def test_all_results_are_signals():
    signals = run_indicators(chain=None, session=_session())
    for s in signals:
        assert isinstance(s, Signal), f"Expected Signal, got {type(s)}"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/indicators/test_registry.py -v
```

- [ ] **Step 3: Create `market/indicators/registry.py`**

```python
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable

from market.signals.types import Signal

logger = logging.getLogger(__name__)


@dataclass
class IndicatorDef:
    name: str
    inputs: list[str]   # type names consumed — for future dependency resolver
    output: str         # type name produced — for future dependency resolver
    fn: Callable


# Ordered list. Indicators run in registration order for the POC.
# inputs/output metadata is captured now; topological sort is deferred.
_REGISTRY: list[IndicatorDef] = []


def indicator(inputs: list[str], output: str, name: str):
    """Register an indicator function. Decorator factory."""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY.append(IndicatorDef(name=name, inputs=inputs, output=output, fn=fn))
        return fn
    return decorator


def run_indicators(chain: Any, session: Any, **extra_inputs: Any) -> list[Signal]:
    """Run all registered indicators in registration order."""
    signals: list[Signal] = []
    for defn in _REGISTRY:
        try:
            result = defn.fn(chain, session)
            if result is not None:
                signals.append(result)
        except Exception as exc:
            logger.warning("indicator %s failed: %s", defn.name, exc)
    return signals
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/indicators/test_registry.py -v
```

- [ ] **Step 5: Commit**

```bash
git add market/indicators/registry.py tests/market/indicators/
git commit -m "feat: indicator registry — ordered execution, metadata captured for future resolver [co-movy]"
```

---

## Task 8: ingest.py — Schwab chain normalization

**Files:**
- Create: `market/ingest.py`
- Create: `tests/market/fixtures/schwab_chain_spx.json`
- Create: `tests/market/test_ingest.py`

All timezone normalization happens in this file. Schwab `expirationDate` comes back as ISO with UTC offset. `_parse_expiry` extracts the date portion. Nothing inside `market/` ever does timezone conversion — `ingest.py` is the boundary.

- [ ] **Step 1: Create fixture JSON**

Create `tests/market/fixtures/schwab_chain_spx.json`:

```json
{
  "symbol": "$SPX",
  "status": "SUCCESS",
  "underlyingPrice": 5820.5,
  "strategy": "SINGLE",
  "volatility": 14.8,
  "callExpDateMap": {
    "2026-05-17:0": {
      "5790.0": [{
        "putCall": "CALL",
        "symbol": "SPXW  260517C05790000",
        "bid": 31.2, "ask": 31.8, "last": 31.5,
        "totalVolume": 892, "openInterest": 3210,
        "volatility": 15.2, "delta": 0.62, "gamma": 0.018,
        "theta": -9.1, "vega": 2.3,
        "strikePrice": 5790.0,
        "expirationDate": "2026-05-17T20:00:00+00:00",
        "daysToExpiration": 0
      }],
      "5800.0": [{
        "putCall": "CALL",
        "symbol": "SPXW  260517C05800000",
        "bid": 22.5, "ask": 23.0, "last": 22.7,
        "totalVolume": 1523, "openInterest": 4521,
        "volatility": 14.8, "delta": 0.42, "gamma": 0.021,
        "theta": -10.2, "vega": 2.1,
        "strikePrice": 5800.0,
        "expirationDate": "2026-05-17T20:00:00+00:00",
        "daysToExpiration": 0
      }],
      "5810.0": [{
        "putCall": "CALL",
        "symbol": "SPXW  260517C05810000",
        "bid": 14.1, "ask": 14.6, "last": 14.3,
        "totalVolume": 2011, "openInterest": 5103,
        "volatility": 14.2, "delta": 0.28, "gamma": 0.019,
        "theta": -9.8, "vega": 1.9,
        "strikePrice": 5810.0,
        "expirationDate": "2026-05-17T20:00:00+00:00",
        "daysToExpiration": 0
      }]
    }
  },
  "putExpDateMap": {
    "2026-05-17:0": {
      "5790.0": [{
        "putCall": "PUT",
        "symbol": "SPXW  260517P05790000",
        "bid": 1.5, "ask": 1.8, "last": 1.6,
        "totalVolume": 750, "openInterest": 2800,
        "volatility": 16.1, "delta": -0.38, "gamma": 0.018,
        "theta": -8.5, "vega": 2.1,
        "strikePrice": 5790.0,
        "expirationDate": "2026-05-17T20:00:00+00:00",
        "daysToExpiration": 0
      }],
      "5800.0": [{
        "putCall": "PUT",
        "symbol": "SPXW  260517P05800000",
        "bid": 2.3, "ask": 2.7, "last": 2.5,
        "totalVolume": 980, "openInterest": 3600,
        "volatility": 15.5, "delta": -0.58, "gamma": 0.021,
        "theta": -9.2, "vega": 2.3,
        "strikePrice": 5800.0,
        "expirationDate": "2026-05-17T20:00:00+00:00",
        "daysToExpiration": 0
      }],
      "5810.0": [{
        "putCall": "PUT",
        "symbol": "SPXW  260517P05810000",
        "bid": 4.1, "ask": 4.5, "last": 4.3,
        "totalVolume": 1200, "openInterest": 4100,
        "volatility": 15.0, "delta": -0.72, "gamma": 0.019,
        "theta": -8.9, "vega": 2.0,
        "strikePrice": 5810.0,
        "expirationDate": "2026-05-17T20:00:00+00:00",
        "daysToExpiration": 0
      }]
    }
  }
}
```

- [ ] **Step 2: Write failing tests**

Create `tests/market/test_ingest.py`:

```python
import json
from pathlib import Path
from datetime import date
from market.ingest import chain_from_schwab
from market.entities.chain import Chain, strike_key
from market.entities.instrument import Contract

FIXTURE = Path(__file__).parent / "fixtures" / "schwab_chain_spx.json"

def _data():
    return json.loads(FIXTURE.read_text())

def test_chain_from_schwab_returns_chain():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert isinstance(chain, Chain)

def test_chain_underlying():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert chain.underlying == "$SPX"
    assert chain.underlying_price == 5820.5

def test_chain_calls_indexed_by_int_key():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert strike_key(5800.0) in chain.calls
    c = chain.call(5800.0)
    assert isinstance(c, Contract)
    assert c.strike == 5800.0
    assert c.contract_type == "CALL"
    assert c.delta == 0.42

def test_chain_puts_indexed_by_int_key():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    p = chain.put(5800.0)
    assert p.contract_type == "PUT"
    assert p.delta == -0.58

def test_no_float_keys():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    for k in chain.calls:
        assert isinstance(k, int), f"Expected int key, got {type(k)}: {k}"
    for k in chain.puts:
        assert isinstance(k, int), f"Expected int key, got {type(k)}: {k}"

def test_contract_symbol_preserved():
    chain = chain_from_schwab(_data(), expiry=date(2026, 5, 17))
    assert chain.call(5810.0).symbol == "SPXW  260517C05810000"
```

- [ ] **Step 3: Run — expect FAIL**

```bash
python -m pytest tests/market/test_ingest.py -v
```

- [ ] **Step 4: Create `market/ingest.py`**

```python
"""
Boundary layer: raw external data -> typed market entities.

All timezone normalization happens here. Everything that enters from
Schwab or Mancini is raw dict/string. Everything that exits is a typed
entity with US/Central datetimes.
"""
from __future__ import annotations
from datetime import date, datetime
from zoneinfo import ZoneInfo

from market.entities.chain import Chain, strike_key
from market.entities.instrument import Contract
from market.entities.level import Level
from market.entities.session import Session

CENTRAL = ZoneInfo("America/Chicago")


def chain_from_schwab(data: dict, expiry: date) -> Chain:
    """Normalize a Schwab get_option_chain() response to a typed Chain.

    Only processes the single expiry matching the `expiry` argument.
    Schwab keys expiry maps as "YYYY-MM-DD:DTE" (e.g. "2026-05-17:0").
    """
    underlying = data.get("symbol", "")
    underlying_price = float(data.get("underlyingPrice", 0.0))
    expiry_prefix = expiry.isoformat()

    calls: dict[int, Contract] = {}
    for exp_key, strikes in data.get("callExpDateMap", {}).items():
        if not exp_key.startswith(expiry_prefix):
            continue
        for strike_str, contracts in strikes.items():
            if not contracts:
                continue
            key = strike_key(float(strike_str))
            calls[key] = _contract_from_schwab(contracts[0], underlying, "CALL")

    puts: dict[int, Contract] = {}
    for exp_key, strikes in data.get("putExpDateMap", {}).items():
        if not exp_key.startswith(expiry_prefix):
            continue
        for strike_str, contracts in strikes.items():
            if not contracts:
                continue
            key = strike_key(float(strike_str))
            puts[key] = _contract_from_schwab(contracts[0], underlying, "PUT")

    return Chain(
        underlying=underlying,
        expiry=expiry,
        calls=calls,
        puts=puts,
        underlying_price=underlying_price,
    )


def session_from_mancini(
    email: "ManciniEmail",
    quote: dict,
    session_date: date,
    vix: float,
    gex_posture: str,
) -> Session:
    """Build a Session from a parsed Mancini email and a Schwab quote dict.

    `quote` is from schwab client.get_quote('$SPX').json()['$SPX']['quote'].
    `gex_posture` is caller-supplied — not derivable from Mancini or quote.
    """
    from mancini.parser import Level as ManciniLevel

    def _bridge(ml: ManciniLevel, label: str) -> Level:
        return Level(price=ml.price, label=label, source="mancini", annotation=ml.annotation)

    supports    = tuple(_bridge(l, "support")    for l in email.support_levels)
    resistances = tuple(_bridge(l, "resistance") for l in email.resistance_levels)

    return Session(
        date=session_date,
        underlying_price=float(quote.get("mark", quote.get("lastPrice", 0.0))),
        open=float(quote.get("openPrice", 0.0)),
        high=float(quote.get("highPrice", 0.0)),
        low=float(quote.get("lowPrice", 0.0)),
        gex_posture=gex_posture,
        vix=vix,
        mancini_supports=supports,
        mancini_resistances=resistances,
    )


def _contract_from_schwab(raw: dict, underlying: str, side: str) -> Contract:
    return Contract(
        symbol=raw.get("symbol", ""),
        underlying=underlying,
        strike=float(raw.get("strikePrice", 0.0)),
        expiry=_parse_expiry(raw.get("expirationDate", "")),
        contract_type=side,
        bid=float(raw.get("bid", 0.0)),
        ask=float(raw.get("ask", 0.0)),
        last=float(raw.get("last", 0.0)),
        volume=int(raw.get("totalVolume", 0)),
        open_interest=int(raw.get("openInterest", 0)),
        delta=float(raw.get("delta", 0.0)),
        gamma=float(raw.get("gamma", 0.0)),
        theta=float(raw.get("theta", 0.0)),
        vega=float(raw.get("vega", 0.0)),
        implied_volatility=float(raw.get("volatility", 0.0)),
    )


def _parse_expiry(expiration_date: str) -> date:
    if not expiration_date:
        return date.today()
    return datetime.fromisoformat(expiration_date).date()
```

- [ ] **Step 5: Run — expect PASS**

```bash
python -m pytest tests/market/test_ingest.py -v
```
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add market/ingest.py tests/market/test_ingest.py tests/market/fixtures/
git commit -m "feat: ingest.py chain_from_schwab + session_from_mancini — boundary layer [co-movy]"
```

---

## Task 9: ingest.py — Mancini session normalization tests

**Files:**
- Create: `tests/market/test_ingest_session.py`

`session_from_mancini` was written in Task 8. This task adds its test coverage.

- [ ] **Step 1: Write failing tests**

Create `tests/market/test_ingest_session.py`:

```python
from datetime import date
from mancini.parser import Level as ManciniLevel, ManciniEmail
from market.ingest import session_from_mancini
from market.entities.session import Session
from market.entities.level import Level

def _email() -> ManciniEmail:
    return ManciniEmail(
        date="2026-05-17", subject="Mancini Daily",
        support_levels=[
            ManciniLevel(price=5780.0, annotation=""),
            ManciniLevel(price=5750.0, annotation="major"),
        ],
        resistance_levels=[ManciniLevel(price=5850.0, annotation="")],
        basic_themes="Range day likely",
    )

def _quote() -> dict:
    return {"mark": 5820.5, "openPrice": 5800.0, "highPrice": 5840.0, "lowPrice": 5795.0}

def test_session_returns_session():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    assert isinstance(s, Session)

def test_session_fields():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    assert s.date == date(2026, 5, 17)
    assert s.underlying_price == 5820.5
    assert s.gex_posture == "negative"
    assert s.vix == 14.8

def test_supports_bridged():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    assert len(s.mancini_supports) == 2
    assert all(isinstance(lev, Level) for lev in s.mancini_supports)
    assert s.mancini_supports[0].source == "mancini"

def test_major_annotation_preserved():
    s = session_from_mancini(_email(), _quote(), date(2026, 5, 17), vix=14.8, gex_posture="negative")
    major = next(l for l in s.mancini_supports if l.price == 5750.0)
    assert major.annotation == "major"

def test_session_no_regime():
    import dataclasses
    fields = {f.name for f in dataclasses.fields(Session)}
    assert "regime" not in fields
```

- [ ] **Step 2: Run — expect PASS** (implementation already exists from Task 8)

```bash
python -m pytest tests/market/test_ingest_session.py -v
```
Expected: all passed. If `ManciniEmail` constructor differs, inspect `mancini/parser.py` and adjust the `_email()` fixture.

- [ ] **Step 3: Commit**

```bash
git add tests/market/test_ingest_session.py
git commit -m "test: session_from_mancini coverage [co-movy]"
```

---

## Task 10: resolve.py — butterfly resolution

**Files:**
- Create: `market/resolve.py`
- Create: `tests/market/test_resolve.py`

`ButterflyTemplate.center` supports three forms:
- `"ATM"` — nearest available strike to `chain.underlying_price`
- `"ATM+5"` / `"ATM-5"` — offset from ATM in points
- Absolute strike as a string: `"5800"`

`ResolutionError` is raised (not returned) when a required strike is absent from the chain. Callers should catch it and decide whether to skip, alert, or retry with a wider chain.

- [ ] **Step 1: Write failing tests**

Create `tests/market/test_resolve.py`:

```python
import json, pytest
from pathlib import Path
from datetime import date
from market.ingest import chain_from_schwab
from market.entities.spread import ButterflyTemplate, ButterflyInstance
from market.resolve import resolve_butterfly, ResolutionError

FIXTURE = Path(__file__).parent / "fixtures" / "schwab_chain_spx.json"

def _chain():
    return chain_from_schwab(json.loads(FIXTURE.read_text()), expiry=date(2026, 5, 17))

def test_resolve_atm():
    t = ButterflyTemplate(center="ATM", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert isinstance(result, ButterflyInstance)
    assert result.lower.strike < result.center.strike < result.upper.strike
    assert result.center.strike - result.lower.strike == 10.0
    assert result.upper.strike - result.center.strike == 10.0

def test_resolve_absolute_strike():
    t = ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert result.center.strike == 5800.0
    assert result.lower.strike == 5790.0
    assert result.upper.strike == 5810.0

def test_net_debit_positive():
    t = ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert result.net_debit > 0

def test_breakevens_bracket_center():
    t = ButterflyTemplate(center="5800", width=10, expiry="0DTE", contract_type="CALL")
    result = resolve_butterfly(t, _chain())
    assert result.lower.strike < result.breakeven_lower < result.center.strike
    assert result.center.strike < result.breakeven_upper < result.upper.strike

def test_missing_strike_raises_resolution_error():
    t = ButterflyTemplate(center="5750", width=10, expiry="0DTE", contract_type="CALL")
    with pytest.raises(ResolutionError):
        resolve_butterfly(t, _chain())
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/test_resolve.py -v
```

- [ ] **Step 3: Create `market/resolve.py`**

```python
from __future__ import annotations
from market.entities.chain import Chain, strike_key
from market.entities.spread import ButterflyTemplate, ButterflyInstance


class ResolutionError(Exception):
    """Required strike unavailable in the chain."""


def resolve_butterfly(template: ButterflyTemplate, chain: Chain) -> ButterflyInstance:
    """Resolve a ButterflyTemplate against a Chain into a ButterflyInstance.

    Raises ResolutionError if any leg strike is absent.
    """
    center = _resolve_center(template, chain)
    lower  = center - template.width
    upper  = center + template.width

    source = chain.calls if template.contract_type == "CALL" else chain.puts
    for s in (lower, center, upper):
        if strike_key(s) not in source:
            raise ResolutionError(
                f"Strike {s} not in {chain.underlying} {chain.expiry} {template.contract_type} chain"
            )

    lc = source[strike_key(lower)]
    cc = source[strike_key(center)]
    uc = source[strike_key(upper)]

    net_debit   = round(lc.mid - 2 * cc.mid + uc.mid, 4)
    max_profit  = round(template.width - net_debit, 4)
    max_loss    = round(net_debit, 4)
    be_lower    = round(lower + net_debit, 4)
    be_upper    = round(upper - net_debit, 4)

    return ButterflyInstance(
        template=template, lower=lc, center=cc, upper=uc,
        net_debit=net_debit, max_profit=max_profit, max_loss=max_loss,
        breakeven_lower=be_lower, breakeven_upper=be_upper,
    )


def _resolve_center(template: ButterflyTemplate, chain: Chain) -> float:
    spec = template.center.strip()
    if spec == "ATM":
        return _nearest(chain.underlying_price, chain, template.contract_type)
    if spec.startswith("ATM"):
        sign   = 1 if "+" in spec else -1
        offset = float(spec.replace("ATM+", "").replace("ATM-", "")) * sign
        return _nearest(chain.underlying_price + offset, chain, template.contract_type)
    return float(spec)


def _nearest(price: float, chain: Chain, side: str) -> float:
    source = chain.calls if side == "CALL" else chain.puts
    best   = min(source.keys(), key=lambda k: abs(k - strike_key(price)))
    return source[best].strike
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/test_resolve.py -v
```

- [ ] **Step 5: Commit**

```bash
git add market/resolve.py tests/market/test_resolve.py
git commit -m "feat: resolve_butterfly — ButterflyTemplate + Chain -> ButterflyInstance [co-movy]"
```

---

## Task 11: gex_regime indicator — end-to-end proof of concept

**Files:**
- Create: `market/indicators/gex.py`
- Create: `tests/market/indicators/test_gex.py`

Full pipeline test: fixture JSON → `chain_from_schwab` → `session_from_mancini` → `gex_regime` → `Regime` signal. If this passes, the entity model is load-bearing end to end.

**GEX logic:** `session.gex_posture` is set externally (SpotGamma, Market Chameleon, etc.) and carried on `Session`. This indicator translates posture + VIX into a typed `Regime`. Real GEX calculation from chain data is deferred — the indicator signature is correct; the internal logic hardens over time.

- [ ] **Step 1: Write failing tests**

Create `tests/market/indicators/test_gex.py`:

```python
import json
from pathlib import Path
from datetime import date
from zoneinfo import ZoneInfo
from market.ingest import chain_from_schwab, session_from_mancini
from market.entities.session import Session
from market.signals.types import Regime
from market.indicators.gex import gex_regime
from mancini.parser import ManciniEmail, Level as ManciniLevel

FIXTURE = Path(__file__).parent.parent / "fixtures" / "schwab_chain_spx.json"
CENTRAL = ZoneInfo("America/Chicago")

def _chain():
    return chain_from_schwab(json.loads(FIXTURE.read_text()), expiry=date(2026, 5, 17))

def _session(gex_posture: str, vix: float = 14.8) -> Session:
    email = ManciniEmail(
        date="2026-05-17", subject="test",
        support_levels=[ManciniLevel(price=5780.0, annotation="")],
        resistance_levels=[ManciniLevel(price=5850.0, annotation="")],
    )
    quote = {"mark": 5820.5, "openPrice": 5800.0, "highPrice": 5840.0, "lowPrice": 5795.0}
    return session_from_mancini(email, quote, date(2026, 5, 17), vix=vix, gex_posture=gex_posture)

def test_returns_regime():
    result = gex_regime(_chain(), _session("negative"))
    assert isinstance(result, Regime)

def test_source_is_gex_regime():
    result = gex_regime(_chain(), _session("negative"))
    assert result.source == "gex_regime"

def test_confidence_in_range():
    result = gex_regime(_chain(), _session("negative"))
    assert 0.0 <= result.confidence <= 1.0

def test_reason_nonempty():
    result = gex_regime(_chain(), _session("negative"))
    assert result.reason

def test_positive_gex_low_vix_is_compressed():
    result = gex_regime(_chain(), _session("positive", vix=11.0))
    assert result.state == "compressed"

def test_positive_gex_normal_vix_is_ranging():
    result = gex_regime(_chain(), _session("positive", vix=15.0))
    assert result.state == "ranging"

def test_negative_gex_high_vix_is_volatile():
    result = gex_regime(_chain(), _session("negative", vix=22.0))
    assert result.state == "volatile"

def test_negative_gex_normal_vix_is_trending():
    result = gex_regime(_chain(), _session("negative", vix=15.0))
    assert result.state == "trending"

def test_timestamp_is_central():
    result = gex_regime(_chain(), _session("neutral"))
    assert result.timestamp.tzinfo == CENTRAL

def test_full_pipeline():
    """Integration: fixture JSON -> entities -> indicator -> Regime signal."""
    chain = _chain()
    session = _session("negative")
    result = gex_regime(chain, session)
    assert isinstance(result, Regime)
    assert result.state in ("trending", "ranging", "volatile", "compressed")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/indicators/test_gex.py -v
```

- [ ] **Step 3: Create `market/indicators/gex.py`**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from market.entities.chain import Chain
from market.entities.session import Session
from market.indicators.registry import indicator
from market.signals.types import Regime

CENTRAL = ZoneInfo("America/Chicago")


@indicator(inputs=["Chain", "Session"], output="Regime", name="gex_regime")
def gex_regime(chain: Chain, session: Session) -> Regime:
    """Translate GEX posture + VIX into a market Regime signal.

    Positive GEX: dealers are long gamma. They sell rallies, buy dips,
    suppressing volatility. Result: compressed or ranging conditions.

    Negative GEX: dealers are short gamma. They buy rallies, sell dips,
    amplifying directional moves. Result: trending or volatile conditions.

    GEX posture is set externally on Session. Real GEX calculation from
    chain data (gamma exposure by strike) is deferred to a future revision.
    """
    now     = datetime.now(tz=CENTRAL)
    posture = session.gex_posture
    vix     = session.vix

    if posture == "positive":
        if vix < 13:
            return Regime(
                timestamp=now, source="gex_regime", confidence=0.8,
                reason=f"Positive GEX + low VIX ({vix:.1f}): dealers suppressing moves",
                state="compressed",
            )
        return Regime(
            timestamp=now, source="gex_regime", confidence=0.7,
            reason=f"Positive GEX + VIX {vix:.1f}: mean-reverting conditions",
            state="ranging",
        )

    if posture == "negative":
        if vix > 20:
            return Regime(
                timestamp=now, source="gex_regime", confidence=0.8,
                reason=f"Negative GEX + elevated VIX ({vix:.1f}): amplified moves expected",
                state="volatile",
            )
        return Regime(
            timestamp=now, source="gex_regime", confidence=0.65,
            reason=f"Negative GEX + VIX {vix:.1f}: directional bias, watch for follow-through",
            state="trending",
        )

    return Regime(
        timestamp=now, source="gex_regime", confidence=0.4,
        reason=f"Neutral GEX + VIX {vix:.1f}: no strong regime bias",
        state="ranging",
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/indicators/test_gex.py -v
```

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/market/ -v
```
Expected: all tests pass. Fix any failures before committing.

- [ ] **Step 6: Commit**

```bash
git add market/indicators/gex.py tests/market/indicators/test_gex.py
git commit -m "feat: gex_regime indicator — end-to-end pipeline proof [co-movy]"
```

---

## Task 12: present/ layer — regime and signals panes

**Files:**
- Create: `present/__init__.py`, `present/regime.py`, `present/signals.py`, `present/driver.sh`
- Create: `tests/market/present/test_regime.py`, `tests/market/present/test_signals.py`

Presenters are pure functions: typed inputs → formatted string. No tmux coupling inside the presenter. The driver script handles tmux and uses `load-buffer + paste-buffer` — NOT `send-keys` (`send-keys` injects keystrokes; `paste-buffer` outputs content to the pane).

- [ ] **Step 1: Write failing tests**

Create `tests/market/present/test_regime.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo
from market.entities.session import Session
from market.entities.level import Level
from market.signals.types import Regime
from present.regime import format_regime

CENTRAL = ZoneInfo("America/Chicago")

def _session():
    return Session(
        date=date(2026, 5, 17), underlying_price=5820.5,
        open=5800.0, high=5840.0, low=5795.0,
        gex_posture="negative", vix=14.8,
        mancini_supports=(
            Level(price=5780.0, label="support", source="mancini"),
            Level(price=5750.0, label="support", source="mancini", annotation="major"),
        ),
        mancini_resistances=(Level(price=5850.0, label="resistance", source="mancini"),),
    )

def _regime():
    return Regime(
        timestamp=datetime(2026, 5, 17, 9, 45, tzinfo=CENTRAL),
        source="gex_regime", confidence=0.65,
        reason="Negative GEX + VIX 14.8: directional bias",
        state="trending",
    )

def test_returns_string():
    assert isinstance(format_regime(_regime(), _session()), str)

def test_contains_state():
    out = format_regime(_regime(), _session())
    assert "trending" in out.lower() or "TRENDING" in out

def test_contains_gex_posture():
    out = format_regime(_regime(), _session())
    assert "negative" in out.lower() or "NEG" in out.upper()

def test_contains_vix():
    out = format_regime(_regime(), _session())
    assert "14.8" in out

def test_contains_support_level():
    out = format_regime(_regime(), _session())
    assert "5780" in out or "5750" in out
```

Create `tests/market/present/test_signals.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from market.signals.types import Bias, Alert, Action, Regime
from present.signals import format_signals

CENTRAL = ZoneInfo("America/Chicago")

def _ts():
    return datetime(2026, 5, 17, 9, 45, tzinfo=CENTRAL)

def test_returns_string():
    assert isinstance(format_signals([]), str)

def test_empty_list():
    out = format_signals([])
    assert "no signals" in out.lower() or isinstance(out, str)

def test_shows_bias():
    out = format_signals([
        Bias(timestamp=_ts(), source="gex_regime", confidence=0.8, reason="negative GEX", direction="bearish"),
    ])
    assert "bearish" in out.lower() or "BEARISH" in out

def test_shows_action():
    out = format_signals([
        Action(timestamp=_ts(), source="butterfly_entry", confidence=0.9, reason="conditions met",
               verb="enter_butterfly", params={"center": 5800, "width": 10}),
    ])
    assert "butterfly" in out.lower() or "enter_butterfly" in out

def test_shows_multiple():
    signals = [
        Bias(timestamp=_ts(), source="gex", confidence=0.8, reason="negative GEX", direction="bearish"),
        Alert(timestamp=_ts(), source="risk", confidence=1.0, reason="delta limit", severity="warn", message="limit hit"),
    ]
    out = format_signals(signals)
    assert "bearish" in out.lower() or "BEARISH" in out
    assert "warn" in out.lower() or "WARN" in out
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/market/present/ -v
```

- [ ] **Step 3: Create present/ files**

```bash
mkdir -p present
touch present/__init__.py
```

Create `present/regime.py`:

```python
"""Format regime and session context for the tmux Regime pane."""
from __future__ import annotations
from market.entities.session import Session
from market.signals.types import Regime

_STATE_LABELS = {
    "compressed": "COMPRESSED  ■ low vol expected",
    "ranging":    "RANGING     ↔ mean-reverting",
    "trending":   "TRENDING    → follow-through",
    "volatile":   "VOLATILE    ⚡ amplified moves",
}


def format_regime(regime: Regime, session: Session) -> str:
    lines = [
        "─" * 50,
        f"  REGIME  {_STATE_LABELS.get(regime.state, regime.state.upper())}",
        f"  Confidence: {regime.confidence:.0%}   GEX: {session.gex_posture.upper()}   VIX: {session.vix:.1f}",
        f"  {regime.reason}",
        "─" * 50,
        f"  SPX {session.underlying_price:.2f}   O {session.open:.0f}  H {session.high:.0f}  L {session.low:.0f}",
        "",
        "  SUPPORTS",
    ]
    for lev in sorted(session.mancini_supports, key=lambda l: l.price, reverse=True):
        tag = f" [{lev.annotation}]" if lev.annotation else ""
        lines.append(f"    {lev.price:>8.1f}{tag}")
    lines += ["", "  RESISTANCES"]
    for lev in sorted(session.mancini_resistances, key=lambda l: l.price):
        tag = f" [{lev.annotation}]" if lev.annotation else ""
        lines.append(f"    {lev.price:>8.1f}{tag}")
    lines.append("─" * 50)
    return "\n".join(lines)
```

Create `present/signals.py`:

```python
"""Format the signal feed for the tmux Signals pane."""
from __future__ import annotations
from market.signals.types import Signal, Bias, Alert, Action, Regime, InferenceRequest

_LABELS = {Bias: "BIAS", Regime: "REGIME", Alert: "ALERT", Action: "ACTION", InferenceRequest: "INFER"}


def format_signals(signals: list[Signal]) -> str:
    if not signals:
        return "  (no signals)"
    lines = ["─" * 60, "  SIGNALS"]
    for sig in signals:
        label = _LABELS.get(type(sig), "SIG")
        ts    = sig.timestamp.strftime("%H:%M:%S")
        conf  = f"{sig.confidence:.0%}"
        lines.append(f"  {ts}  [{label:<6}] {conf}  {sig.source}  {_detail(sig)}")
    lines.append("─" * 60)
    return "\n".join(lines)


def _detail(sig: Signal) -> str:
    if isinstance(sig, Bias):         return f"{sig.direction.upper()}  {sig.reason}"
    if isinstance(sig, Alert):        return f"{sig.severity.upper()}  {sig.message}"
    if isinstance(sig, Action):       return f"{sig.verb}  {sig.params}"
    if isinstance(sig, Regime):       return f"{sig.state.upper()}  {sig.reason}"
    if isinstance(sig, InferenceRequest): return f"→ {sig.question}"
    return sig.reason
```

Create `present/driver.sh`:

```bash
#!/usr/bin/env bash
# Update a tmux pane with presenter output.
# Usage: driver.sh <presenter> <pane_target>
#   presenter:   regime | signals
#   pane_target: tmux address, e.g. "strader:Dashboard.1"
#
# Uses load-buffer + paste-buffer. NOT send-keys.
# send-keys injects keystrokes; paste-buffer outputs content to the pane display.

set -euo pipefail

PRESENTER="${1:?Usage: driver.sh <presenter> <pane_target>}"
PANE="${2:?Usage: driver.sh <presenter> <pane_target>}"
shift 2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
source .venv/bin/activate

case "$PRESENTER" in
  regime)
    python -m present.cli regime "$@" | tmux load-buffer - && tmux paste-buffer -t "$PANE"
    ;;
  signals)
    python -m present.cli signals "$@" | tmux load-buffer - && tmux paste-buffer -t "$PANE"
    ;;
  *)
    echo "Unknown presenter: $PRESENTER" >&2
    exit 1
    ;;
esac
```

```bash
chmod +x present/driver.sh
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/market/present/ -v
```

- [ ] **Step 5: Run full suite — all green**

```bash
python -m pytest tests/market/ -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add present/ tests/market/present/
git commit -m "feat: present/ layer — regime and signals formatters, tmux driver [co-movy]"
```

---

## Spec Coverage

| Spec section | Implemented in |
|---|---|
| Problem — no shared entity layer | Tasks 2–6 |
| Principle 1: code not inference | `Action` noted as recommendation; gate key note in `types.py` |
| Principle 2: instrument-centric | `Contract` is the atom; all spreads compose from it |
| Principle 3: template + instance | Tasks 5, 10 |
| Principle 4: pure functions | `@indicator` on pure functions; Task 11 |
| Principle 5: inference escape hatch | `InferenceRequest` in Task 1; `FootprintSnapshot` marked illustrative in code |
| Global convention: US/Central | `CENTRAL = ZoneInfo("America/Chicago")` in `ingest.py`, `gex.py`; `Signal.timestamp` comment |
| Entity layer (all types) | Tasks 2–6 |
| Signal types | Task 1 |
| Indicator registry | Task 7 |
| gex_regime | Task 11 |
| resolve.py | Task 10 |
| ingest.py (Schwab + Mancini) | Tasks 8–9 |
| present/ (regime, signals) | Task 12 |
| Module structure | File map matches spec |
| Boundary: `market/` zero external deps | Enforced by structure; only `ingest.py` imports from `mancini/` |
| Testing strategy | Unit per entity/indicator; integration test in Task 11 |
| Implementation sequence | Tasks follow spec sequence |
