# Orderflow Signal Layer — Design of Record

**Bead:** st-l5o · **Date:** 2026-07-03 · **Status:** Design of record — Steve's review ongoing; amendments expected (Phase A/B timing clarification approved 2026-07-03)
**Companion research:** `docs/research/2026-07-03-orderflow-primitives-research.md` (Q1–Q3 deep dive with sources; also the learning document for the primitives and setup signatures)

---

## 1. Purpose and boundary

A new module family under `market/` that consumes the DataBento ES stream (trades + MBP-1 quotes) and emits **orderflow signals**: the trigger substrate for the four consumers the playbook system already declares:

1. **Carmine setup recognition** — the `CarmineSetup` taxonomy in `strader/entities/singleton.py` (`failed_breakdown`, `level_reclaim`, `return_to_lvn`, `range_trap`) is "recognized from the feed"; this layer is that recognition.
2. **`orderflow-confirm`** (and `return-to-lvn`) Tier-2 entry tags in `strader/playbooks/conditions.yaml`.
3. **Day-classifier confluence** — the `mancini_carmine_confluence` input in `strader/evaluate/day_classifier.py`.
4. **Singleton triggers** — a confirmed recognition supplies everything `SingletonSetup` needs.

**Non-goals (explicit boundary):** no order routing, no automated entry (Actions remain recommendations; the Schwab gate-key boundary is never bypassed). GEX stays out entirely while GexBot is paused. Measured-edge / backtest scoring is deferred (co-wh19 §10 item 3) — but the corpus + replay determinism built here is what makes it possible later.

**Philosophy (carried from the butterfly doctrine):** *score, don't gate.* Every output is graded evidence for a discretionary trader, never a binary classification gate. A setup with 3 of 4 evidence beats is a weaker instance, not a non-event.

---

## 2. Q1 — v1 primitive set (RESOLVED)

Six primitives in two tiers (full definitions, computations, and pitfalls in the companion research doc §Q1):

**Tier A — deterministic per-event primitives (v1 core, trades-only):**

| Primitive | One-line definition | Key config |
|---|---|---|
| Cumulative delta (CVD) | Running (buy-aggressor − sell-aggressor) volume | reset = RTH open 08:30 CT; `None`-side prints bucketed separately, never folded into delta |
| Delta divergence | Price extreme not confirmed by CVD extreme | deterministic swing-pivot rule (N-tick filter) |
| Footprint imbalance | Diagonal bid/ask dominance at a price within a bar | ratio 3.0×, floor 100 contracts, stacked = 3 consecutive |
| Large-lot / sweep | Outsized single print / one aggressor walking ≥N ticks in T ms | k× rolling-median size; sweep span + window |

**Tier B — structural context and scored reads:**

| Primitive | Role | Constraint |
|---|---|---|
| LVN / volume profile | *Where* to watch — levels context, recomputed per completed session | window convention named in config |
| Absorption | *Scored read* (0–1 + exposed evidence), never a boolean in v1 | needs MBP-1 → phases in with live quote capture (§7) |

CME provides exchange-tagged aggressor side (Tag 5797) via DataBento's `side` field — delta primitives on ES are computed, not inferred. All thresholds are named config constants (§9), never inline magic numbers.

---

## 3. Q2 — Setup signatures: one shared four-beat engine (RESOLVED)

All four Carmine setups decompose into the same rhythm:

> **Beat 1 — aggression pushes past a level** (flush/poke, delta burst, possible sweep)
> **Beat 2 — failure of acceptance** (absorption or no-follow-through: aggression continues, price stops moving)
> **Beat 3 — delta flips or diverges** (CVD turns; price extreme unconfirmed by delta)
> **Beat 4 — reversal confirmed** (opposite-side stacked imbalances as price re-takes the level)

Altitude note: the beats consume primitive *events*, not raw footprint cells. "Stacked imbalance" in beat 4 is the finished output of the diagonal cell test (§2; research doc Q1.3) — the diagonal arithmetic happens one layer down, inside the bar builder; by the time a signature sees it, it is just an event ("stacked buy imbalance at 7541–7542, bar #412"). Same for "absorption" (a score) and "delta flip" (a CVD read). The recognizer reads the lab report; the microscope work is already done.

What varies per setup is the **level type**, **direction**, and **intensity profile**:

| Setup | Level | Break | Resolution | Confidence in signature |
|---|---|---|---|---|
| `failed_breakdown` | support (prior low, Mancini level) | violent flush down | reclaim up | High (Mancini-grounded) |
| `level_reclaim` | any lost level | quiet loss | reclaim + hold on retests | Medium-high (synthesis) |
| `return_to_lvn` | LVN | approach (either way) | reject **or** accept — delta-stall-and-flip vs delta-extend discriminates | Medium (proposed; validate on tape) |
| `range_trap` | range edge / VAH–VAL | breakout poke | reverse back inside | High (failed-auction literature) |

**Implementation consequence:** one `SetupRecognizer` parameterized by (level type, direction, intensity thresholds) — not four bespoke detectors. Build order: `failed_breakdown` + `range_trap` (shared machinery, best grounded) → `level_reclaim` (encode the flush-intensity discriminator so it doesn't collapse into failed_breakdown) → `return_to_lvn` (most synthetic; ship flagged as proposed).

Recognition is stateful per (setup, level): `forming → confirmed | invalidated`, with each beat's evidence carried on the emitted signal so the human sees *why*.

---

## 4. Q3 — Unit model: event core + footprint-over-volume-bars (RESOLVED)

**Layered model:**

1. **Event-driven core is the source of truth.** Every Trade/Quote processed in stream order; running state (CVD, book, sweep/large-lot detection, profile accumulation) updates per event. Sequence-sensitive primitives live here at full resolution.
2. **Footprint bars are a derived reduction** — per-price (ES tick 0.25) bid/ask volume within a bar; required for imbalance and absorption.
3. **Volume bars are the footprint base** (not time bars): boundary = cumulative-contract threshold → wall-clock-free, replay-exact, activity-normalized. Straddle rule: the whole crossing trade lands in the bar it crosses into completion (no splitting). `VOLUME_BAR_N` is calibrated once from corpus data (target: median RTH bar duration in the 30–60s range), then frozen as config.
4. **1-minute time bars remain a display/alignment layer only** (matches OHLCV feed and how Mancini levels are drawn) — never the computation substrate.
5. **No range bars in v1.**

**Determinism rules (load-bearing, enforced everywhere):**
- Order and bucket only by stream `ts_event` + sequence number. Never wall-clock, never `ts_recv`, never arrival order.
- Timestamp ties break by sequence number.
- All intervals half-open; all threshold-crossing rules written down once (§9).
- Any warm-up windows (rolling medians) seeded identically live and replay.

---

## 5. Q4 — Live/replay contract (CONSTRAINT, not open)

One engine, two adapters:

```
OrderflowEngine.process(event: Trade | Quote) -> list[Signal]
```

- **Live adapter:** wraps `market/ingest/databento.py` `LiveClient`. Note: `LiveClient` currently exposes `trades()` and `quotes()` as separate iterators over the same session; the engine needs a single merged `events()` iterator in stream order — a small ingest extension, listed as implementation work.
- **Replay adapter:** iterates the corpus (per-day JSONL trade files; DBN archives via `DBNStore.from_file()` where teed) and feeds the identical `process()`.

**Parity is proven, not assumed:** a golden-output test replays a recorded corpus day and asserts the exact signal sequence (type, timestamp, payload) against a committed fixture. Any engine change that alters output fails CI until the fixture is deliberately regenerated. This is the acceptance test for the whole layer.

---

## 6. Q5 — Output shape (RESOLVED)

**Extend the existing `Signal` hierarchy — no parallel tree.** Data artifacts (bars) go in `market/entities/`; interpretations go in `market/signals/`. Prototype definitions (the bead's prototype deliverable; landed as code under the first implementation bead):

```python
# market/entities/footprint.py
@dataclass(frozen=True)
class FootprintCell:
    price: float          # ES tick-bucketed (0.25)
    bid_vol: int          # sell-aggressor volume (hit the bid)
    ask_vol: int          # buy-aggressor volume (lifted the offer)

@dataclass(frozen=True)
class FootprintBar:
    symbol: str
    start_ts: datetime    # ts_event of first print, US/Central
    end_ts: datetime      # ts_event of last print
    open: float; high: float; low: float; close: float
    volume: int           # == VOLUME_BAR_N (± straddle overshoot)
    delta: int            # bar buy-aggr − sell-aggr
    none_vol: int         # aggressor-less prints, tracked, never in delta
    cells: tuple[FootprintCell, ...]   # ascending price

# market/signals/orderflow.py — all subclass Signal (timestamp, source, confidence, reason)
@dataclass(frozen=True)
class SweepPrint(Signal):
    direction: Literal["buy", "sell"] = "buy"
    ticks_swept: int = 0
    total_size: int = 0

@dataclass(frozen=True)
class DeltaDivergence(Signal):
    kind: Literal["bullish", "bearish"] = "bullish"
    price_extreme: float = 0.0
    cvd_at_extreme: int = 0
    cvd_at_prior: int = 0

@dataclass(frozen=True)
class ImbalanceStack(Signal):
    direction: Literal["buy", "sell"] = "buy"
    prices: tuple[float, ...] = ()
    ratios: tuple[float, ...] = ()

@dataclass(frozen=True)
class AbsorptionRead(Signal):
    # confidence carries the score; components exposed, never a boolean
    price: float = 0.0
    aggressive_vol: int = 0
    displacement_ticks: int = 0
    refill_events: int = 0          # MBP-1-derived; 0 when quotes unavailable

@dataclass(frozen=True)
class SetupRecognition(Signal):
    setup: CarmineSetup = "failed_breakdown"
    bias: Literal["bullish", "bearish"] = "bullish"
    anchor: Level | None = None
    state: Literal["forming", "confirmed", "invalidated"] = "forming"
    beats: tuple[str, ...] = ()     # which of the four beats have fired
    mancini_confluence: bool = False
```

**Consumer wiring:**
- `SetupRecognition(state="confirmed")` carries exactly the fields `SingletonSetup(bias, trigger, anchor, mancini_confluence)` needs — direct construction.
- `orderflow-confirm` tag = a confirmed recognition (or standalone directional evidence: delta flip + imbalance stack agreeing with the entry direction).
- `mancini_carmine_confluence` classifier input = any recognition whose anchor coincides with a live Mancini level (tolerance in config).
- `InferenceRequest` (already in `types.py`) remains the escape hatch for reads the deterministic engine can't produce; the reserved `FootprintSnapshot` idea is realized as `FootprintBar`.

---

## 7. Corpus and data plan (Steve directives, 2026-07-03)

- The 13:00–15:00 CT window is **butterfly-specific**; orderflow needs the **full cash session 08:30–15:00 CT**.
- **Trades, full RTH, daily:** ~3.25× the probed 2-hour cost ($0.09) ≈ **$0.29/day** — approved as acceptable. Re-verify with `metadata.get_cost` before widening (script already supports `--estimate-only`).
- **MBP-1 quotes: never backfilled.** Quotes are captured **forward** from the live tee (`tee_raw` already archives lossless DBN) once live streaming lands (Phase B below). Absorption's `refill_events` evidence activates when quote capture starts; until then absorption scores run trades-only (volume + displacement, degraded and labeled as such).
- **Overnight (Globex):** decision 2026-07-03 — skip for the interim; Phase B's round-the-clock capture makes it moot. Revisit only if the 8/1 upgrade slips.

**Live vs. historical phasing (per co-s7zw, decided 2026-07-01):**

| Phase | Window | Data reality | What runs |
|---|---|---|---|
| **A** | now → 8/1 | Historical batch T&S only (corpus pulls arrive next morning; Schwab has no futures time & sales; DataBento live streaming requires the CME Standard plan — blocked until the 8/1 subscription renewal, $179/mo + non-pro CME license ≈ $190 all-in) | Build + calibrate + golden-replay the whole layer on corpus data. **TradingView's built-in footprint (+ generated Pine overlays) is the live intraday surface.** |
| **B** | 8/1 → | CME Standard live GLBX streaming: real-time trades + MBP-1, teed to corpus | The orderflow layer runs live in-session; our own live-capture footprint (co-s7zw Phase B) replaces TV's; quote capture begins, absorption gets full evidence. |

Nothing in Phase A work is throwaway: live/replay parity (§5) means the engine built and proven on replay in Phase A is byte-for-byte the engine that goes live in Phase B.

---

## 8. Implementation beads (created 2026-07-03 on approval; built there, not under st-l5o)

1. **st-uqf:** `FootprintCell`/`FootprintBar` entities + deterministic volume-bar builder (straddle rule, tie-breaks) + golden replay test over one corpus day.
2. **st-wnc:** engine core — merged `events()` ingest iterator, CVD (+reset/None policy), large-lot, sweep, swing-pivot detector, `SweepPrint`/`DeltaDivergence` signals.
3. **st-su4:** footprint imbalance + `ImbalanceStack` (diagonal test, thresholds from config).
4. **st-7d6:** LVN / volume-profile context on completed-session cadence; profile levels as `Level` signals.
5. **st-2kf:** four-beat `SetupRecognizer` + `SetupRecognition` lifecycle + consumer wiring (SingletonSetup construction, orderflow-confirm, classifier confluence). `failed_breakdown` + `range_trap` first.
6. **st-f05:** corpus widening — full-RTH ES trades pull (cost re-estimate then flip the default window), `VOLUME_BAR_N` calibration from the widened corpus.
7. **st-d5f:** live quote capture + absorption `refill_events` activation (deferred to 2026-08-01 — Phase B, CME Standard upgrade).
8. **st-bw9:** live/replay parity harness in CI (golden fixture + regeneration protocol).

Suggested order: st-uqf → st-wnc → st-su4 → st-f05, in parallel with st-7d6; then st-2kf → st-bw9; st-d5f when Phase B lands.

---

## 9. Config constants (single source, `market/signals/orderflow_config.py`)

| Constant | Initial value | Note |
|---|---|---|
| `CVD_RESET` | RTH open 08:30 CT | modeling convention |
| `NONE_SIDE_POLICY` | separate bucket | never in delta |
| `TICK` | 0.25 | ES |
| `IMBALANCE_RATIO` | 3.0 | diagonal test |
| `IMBALANCE_FLOOR` | 100 contracts | ES-scale floor |
| `STACK_MIN` | 3 | consecutive imbalances |
| `LARGE_LOT_K` | calibrate from corpus | × rolling median print |
| `SWEEP_MIN_TICKS` / `SWEEP_WINDOW_MS` | calibrate from corpus | event-time only |
| `VOLUME_BAR_N` | calibrate (median bar 30–60s RTH) | then frozen |
| `PIVOT_FILTER_TICKS` | calibrate from corpus | swing definition |
| `CONFLUENCE_TOLERANCE_PTS` | matches existing playbook convention | Mancini∩anchor |

Initial values are starting points from practitioner literature, expected to be tuned; every change is a config commit, never a silent edit.

---

## 10. Resolution log

1. **Spec approved 2026-07-03 (Steve)** — design of record; implementation beads created under st-l5o's close.
2. **Overnight scope:** skip interim Globex pulls; Phase B round-the-clock capture covers it (revisit only if 8/1 slips).
3. **Q2 signatures as teaching material (standing):** the companion research doc §Q2 is the "learn the mapping" deliverable — the four-beat framing and per-setup walkthroughs are written to be read. The `return_to_lvn` two-branch read in particular is proposed, not established. **Validation is empirical, not experiential** (corrected 2026-07-04: Steve is ~5 years into trading, not a veteran chart-reader — 30 years was software): proposed signatures get validated against the corpus (do the sequences precede the outcomes?) and through drill outcomes (st-yfn), not by anyone's accumulated tape intuition.
