# Playbook Entity — Design Spec

**Status:** Approved design (2026-06-26); **implemented 2026-07-02** under
st-c71. Living document — vocabulary and schema expected to be refined iteratively.
**Bead:** co-wh19 (COO-driven; implemented in Strader as st-c71)
**Author flow:** brainstormed COO↔Steve 2026-06-25/26; supersedes the lost
"playbook-as-entity" origin conversation (not recoverable from substrate).

> **Revision (2026-07-02, st-c71).** The entity + evaluator were relocated from
> `market/` to the **`strader` package** — strategy entities live beside
> `singleton.py`. This spec predated the strader2 greenfield restructure (6-29)
> and fold-in (7-2), which established the split: `market/entities/` holds carried
> datafeed primitives, `strader/entities/` holds strategy entities. §3 below is
> updated to the as-built layout. Also as-built: the six InvestiTrade playbooks
> ship `status: worthy`, and YAML is loaded by a stdlib block-YAML subset loader
> (`strader/_yaml.py`) so the core keeps no hard dependency (defers to PyYAML if
> installed).

## 1. Purpose

A **Playbook** is a first-class Strader entity that holds one trading strategy
Steve has curated as worthy — framed structurally the way a Zgent is a
first-class entity. The set of Playbooks is a **curated, version-controlled
catalog** plus a **transparent code-based evaluator** that, given the day's
conditions, surfaces which playbook(s) best fit and instruments their checklists.

It does **not** automate trades. It recommends and equips; Steve decides and acts.

### Primary job (ordered)

1. **Canonical structured record** (this spec): formalize each strategy into a
   standardized, machine-readable file. The InvestiTrade prose becomes data.
2. **Fit evaluator** (this spec): score playbooks against a declared day-context,
   surface best fit, emit that playbook's indicators + checklists.
3. *(Deferred, own brainstorms)* Day-type **classifier** (how the day-context is
   computed) and **live-data binding** (wiring conditions to live/historical market
   entities + the Mancini corpus).

### Three confirmed decisions

- **Structured record first** — the doc is content; the entity is form.
- **Manual curation** — Steve sets `status`; no backtest gates worthiness in v1.
- **Standalone catalog** — v1 does not bind to live market entities; a binding
  layer bolts on later. The evaluator consumes a *declared* day-context.

## 2. Non-goals (v1)

- No trade automation or order routing.
- No automatic day-type classification — the evaluator takes a `DayContext` as
  input; producing it is a separate brainstorm.
- No live or historical market-data binding; no backtest/edge measurement.
- No worthiness automation — status is a human decision.

## 3. Architecture

```
strader/entities/playbook.py            # Playbook, PlaybookCatalog, Vocabulary (§6)
strader/evaluate/playbook_evaluator.py  # PlaybookEvaluator, DayContext, PlaybookScore (§7)
strader/_yaml.py                        # stdlib block-YAML subset loader (no hard dep)
strader/playbooks/                       # the catalog data
  conditions.yaml                       # the living condition vocabulary (§5)
  momentum-breakout.md                  # one file per playbook (§4)
  mean-reversion-fade.md
  trend-continuation-pullback.md
  opening-range-breakout.md
  options-premium-harvest.md
  gap-fill.md
```

Mirrors the frozen-dataclass entity convention (as in `market/entities/`, and
`strader/entities/singleton.py`). The evaluator sits beside the entities in the
`strader` package, not inside them.

### Units and responsibilities

| Unit | Does | Depends on |
|------|------|-----------|
| `conditions.yaml` | Defines the controlled vocabulary of condition tags | nothing |
| `*.md` playbook files | Hold one strategy each (structured frontmatter + prose body) | `conditions.yaml` (tag references) |
| `Playbook` | Load + validate one playbook file | `conditions.yaml` |
| `PlaybookCatalog` | Enumerate/filter the set of playbooks | `Playbook` |
| `DayContext` | A set of currently-true condition tags | `conditions.yaml` |
| `PlaybookEvaluator` | Score playbooks vs a `DayContext`; rank; emit checklists | `PlaybookCatalog`, `DayContext` |

## 4. Playbook file format

One markdown file per playbook. Literal filenames (no abbreviations) —
`momentum-breakout.md`. YAML frontmatter carries the queryable fields; the
markdown body carries the human-oriented narrative fields.

```yaml
---
code: MB                       # stable short id (internal)
name: Momentum Breakout
status: worthy                 # candidate | worthy | active | retired  ← Steve sets
adopted: 2026-06-25            # date it earned its current status
source: InvestiTrade           # provenance: InvestiTrade | Carmine Rosato | Mancini | own | …
instruments: [ES, SPX, singles]
favored_conditions: [trend-up, trend-down, vol-high, gex-neg, room-to-travel]  # PROMOTE
avoid_conditions:   [range-chop, vol-low, near-magnet]                         # DE-EMPHASIZE
indicators: [luxalgo-trend, cumulative-delta, vwap]   # what to watch to support this strat
rationale: "Why Steve curates this as worthy"
updated: 2026-06-26
---
## Thesis
## Setup
## Entry
## Stop
## Targets
## Invalidation
## Sizing
## Regime fit (notes)
## Entry checklist
- [ ] confirmation item …
## Management checklist
- [ ] scaling / runner rule …
```

- `favored_conditions` / `avoid_conditions` draw from `conditions.yaml` Tier-1 tags.
- Entry/management checklist items may reference Tier-2 tags but are free-form
  text in v1.
- The eight body sections are the standardized field set inherited from the
  InvestiTrade Master Reference.
- Win-rate / R-multiple numbers from the source doc are **omitted** in v1 (we are
  not measuring edge yet); a future `measured_edge` block can append when backtest
  binding lands.

## 5. The living condition vocabulary (`conditions.yaml`)

The vocabulary is data, not hardcoded — because it will be refined continuously.
One file lists every condition tag with its definition, tier, and whether it is
objectively computable yet. Playbooks and the evaluator both read it; the entity
validates each playbook's tags against it (typos / retired tags are caught).

```yaml
# conditions.yaml — controlled vocabulary for playbook day-context + entry tags.
# LIVING DOCUMENT: add/rename/retire tags here; everything else references this.
tiers:
  day_context:        # Tier 1 — assessed to RANK playbooks for the day
    trend-up:        { def: "Price grinding higher; higher highs, holds above rising average", objective: partial }
    trend-down:      { def: "Price grinding lower; lower lows, holds below falling average",   objective: partial }
    range-chop:      { def: "No net direction; oscillates in a band, repeated reversals",        objective: partial }
    vol-high:        { def: "Market moving a lot — wide range vs its recent typical range",      objective: true }
    vol-low:         { def: "Quiet, small-range tape",                                           objective: true }
    ivr-high:        { def: "Options expensive vs their own past year (IV Rank high)",           objective: true }
    ivr-low:         { def: "Options cheap vs their own past year (IV Rank low)",                objective: true }
    gex-neg:         { def: "Negative GEX — dealer hedging amplifies moves; pushes run",         objective: true }
    gex-pos:         { def: "Positive GEX — dealer hedging dampens moves; price pins/reverts",   objective: true }
    room-to-travel:  { def: "Price far from nearest magnet/wall; open space to move",            objective: true }
    near-magnet:     { def: "Price at a wall/magnet where it tends to stall or pin",             objective: true }
    gap-up:          { def: "Opened meaningfully above prior close",                             objective: true }
    gap-down:        { def: "Opened meaningfully below prior close",                             objective: true }
    news-scheduled:  { def: "Known calendar event due today (CPI, FOMC, jobs)",                  objective: true }
    news-adhoc:      { def: "Unscheduled headline-driven volatility",                            objective: false }
    at-key-level:    { def: "Price sitting on one of today's Mancini levels",                    objective: true }
    level-to-level-room: { def: "Clear space to the next Mancini level (room to run)",           objective: true }
    mancini-carmine-confluence: { def: "A Mancini level and a Carmine zone coincide at one price — highest conviction", objective: true, weight: high }
  entry_confirmation: # Tier 2 — checked at the moment of entry
    orderflow-confirm:  { def: "Order-flow tools agree (cum delta / footprint show buyers/sellers stepping in)" }
    return-to-lvn:      { def: "Price returned to a low-volume node it ripped through (Carmine core setup)" }
    luxalgo-zone-touch: { def: "Price reached a LuxAlgo supply/demand zone" }
    v-dump-complete:    { def: "Sharp V-shaped drop bottomed and started its return (butterfly entry cue)" }
```

`objective: partial|false` flags tags whose evaluation depends on the deferred
day-type classifier. `weight: high` lets the evaluator privilege Mancini↔Carmine
confluence.

### Mancini as persistent backdrop

Mancini's levels are not one tag among many — they are the **map every evaluation
references** ("where is price in today's Mancini level structure"). Carmine
provides the **trigger** (how to trade a touch). `mancini-carmine-confluence` —
where a Mancini level and a Carmine zone coincide — is the single highest-weight
promote condition (the "echo" Steve wants surfaced). Determinism note: Mancini's
levels are deterministic inputs (we ingest them nightly); the subjective read is
confined to trend/news tags and is the subject of the deferred classifier.

## 6. Entity classes

```python
@dataclass(frozen=True)
class Playbook:
    code: str
    name: str
    status: str                 # candidate | worthy | active | retired
    source: str
    instruments: tuple[str, ...]
    favored_conditions: tuple[str, ...]
    avoid_conditions: tuple[str, ...]
    indicators: tuple[str, ...]
    rationale: str
    adopted: date
    updated: date
    body: str                   # the markdown body (thesis…management checklist)

    @classmethod
    def load(cls, path, vocab) -> "Playbook": ...   # parse frontmatter+body; validate tags vs vocab

class PlaybookCatalog:
    def __init__(self, directory, vocab): ...        # load all *.md
    def all(self) -> list[Playbook]: ...
    def worthy(self) -> list[Playbook]: ...          # status in {worthy, active}
    def by_instrument(self, sym) -> list[Playbook]: ...
```

`Playbook.load` validates every `favored_conditions` / `avoid_conditions` tag
against the loaded vocabulary; an unknown tag is a load-time error with a clear
message (fresh-agent friendly).

## 7. The evaluator

```python
@dataclass(frozen=True)
class DayContext:
    tags: frozenset[str]        # currently-true day_context tags; validated vs vocab
    # how this is produced is the DEFERRED day-type brainstorm

@dataclass(frozen=True)
class PlaybookScore:
    playbook: Playbook
    score: float
    matched_favored: tuple[str, ...]   # WHY it scored — transparency
    matched_avoid: tuple[str, ...]

class PlaybookEvaluator:
    def rank(self, ctx: DayContext) -> list[PlaybookScore]: ...
    def surface(self, ctx: DayContext) -> PlaybookScore | None:  # top pick
        ...
    def instrument(self, score: PlaybookScore) -> dict:          # indicators + checklists for the pick
        ...
```

**Scoring (v1, transparent arithmetic):**
`score = Σ(favored present) − Σ(avoid present)`, with `weight: high` tags
(Mancini↔Carmine confluence) contributing more than 1. Only `worthy`/`active`
playbooks are scored. Every score reports `matched_favored` / `matched_avoid` so
Steve sees *why* a playbook surfaced. Ties are broken deterministically (by
code) and reported, never hidden.

**Output:** ranked playbooks; the top pick's `indicators` to watch and its
entry + management checklists, instrumented for the session.

## 8. Lifecycle

Status is moved by hand, recorded with date + rationale:

```
candidate ─▶ worthy ─▶ active ─▶ retired
                ▲                    │
                └────────────────────┘   (can be reinstated)
```

- `candidate` — under consideration; not yet trusted.
- `worthy` — curated as sound; eligible for the evaluator.
- `active` — currently being traded.
- `retired` — benched but **kept** (never deleted; the record of what was tried
  is itself valuable).

No automation gates these transitions in v1. The entity records and timestamps
Steve's calls.

## 9. Seed content

Initial catalog seeds from the InvestiTrade Master Reference (six playbooks:
Momentum Breakout, Mean Reversion Fade, Trend Continuation Pullback, Opening
Range Breakout, Options Premium Harvest, Gap Fill) plus Steve's own curated
strats (singles-as-futures-proxy, V-dump butterfly). Each is poured into the
file format above. The InvestiTrade regime-compatibility matrix maps directly to
`favored_conditions` / `avoid_conditions`.

## 10. Explicitly deferred (follow-on brainstorms)

1. **Day-type classifier** — how a `DayContext` is computed from market data.
   Design stance already agreed: objective baseline (computed primitives) with a
   logged subjective override; coarse well-separated buckets over fine gradations;
   every assignment auditable; vocabulary driven by what the strats actually
   distinguish ("work backward from the strats"). Determinism preferred over
   precision.
2. **Live/historical data binding** — wiring conditions to Strader market
   entities (GexProfile, Session, Level) and the live + backfilled Mancini corpus.
3. **Measured-edge layer** — backtest each playbook against history; optional
   evidence to inform (not gate) worthiness.

## 11. Testing

- `Playbook.load`: valid file parses; unknown tag → clear error; missing
  required frontmatter → clear error.
- `PlaybookCatalog`: filters (`worthy`, `by_instrument`) return correct subsets.
- `conditions.yaml`: every tag referenced by any playbook exists in the vocab
  (a catalog-wide integrity test).
- `PlaybookEvaluator.rank`: deterministic ordering; `matched_*` correctly report
  the drivers; weighted confluence outranks an equal count of plain tags; ties
  broken by code.
- Round-trip: a hand-written playbook file loads, scores against a sample
  `DayContext`, and instruments without error.
```
