# Trade-Language Normalization — One Entity Model from Spoken Day-Description to TOS Order String

**Bead:** st-79z.1 (Trade Language Front, epic st-79z) · **Synthesized:** 2026-07-25 · **Inputs:** six read-only surveys (Strader code, Mancini vocabulary, Carmine vocabulary, TOS order syntax, standing constraints, spoken intent)

---

## 1. Executive summary

The enterprise already holds most of the middle of the pipeline and neither end. The middle: a mature numbers-side entity model in Strader (`market/entities/`, `market/signals/`, `strader/entities/`), a machine-validated controlled vocabulary (`strader/playbooks/conditions.yaml`, 22 day-context + 4 entry-confirmation tags), a production Mancini parse contract (`runbook/mancini/schema.py` — `ParseResult / Level / Trigger / Commentary`, with trigger types `price_cross, price_zone, time, regime, unconditional`), a live deterministic setup recognizer (four stages flush→stall→flip→confirm), and a butterfly template/resolution chain (`market/entities/spread.py`, `market/resolve.py`). The two ends are greenfield: **no code anywhere parses Steve's spoken language**, and **no TOS order string, generator, or specimen exists anywhere in the enterprise** (verified by repo-wide greps in three independent surveys). The normalized model below defines eleven entities — Level, Trigger, Setup, Regime/DayType, SessionWindow, Intent (conditional branch), StructureTemplate, Order, Bracket, Size/Risk, Position — each carrying an explicit **provenance** attribute and, for anything priced, an explicit **price-frame** attribute (ES vs SPX), because those two missing attributes are the root cause of the enterprise's two known vocabulary incidents (the Mancini–Carmine confluence error, st-1s1, and the ES/SPX basis gap, `docs/foundation/08-es-spx-bridge.md`). Normalization happens at the entity layer only: Mancini's and Carmine's vocabularies remain separate namespaces at the source layer, per the st-1s1 correction — their levels are never claimed to be the same levels. The pipeline terminus is a cut-and-paste TOS string; execution stays human by structural design (hobbled schwab-py fork, `no-autonomous-orders`), not merely by policy.

---

## 2. Source inventory

### 2.1 TOS order-string protocol (execution terminus)

**Role:** the output grammar — the single-line order description Steve pastes into ThinkOrSwim's order editor.

**Key vocabulary:** `BUY/SELL` (working), `BOT/SOLD` (filled), signed quantity (`+1`/`-2`), spread-type keywords (`VERTICAL`, `BUTTERFLY`, `IRON CONDOR`, `CONDOR`; `UNBALANCED_*` corroborated by schwab-py enum), underlying + `100` multiplier + `(Weeklys)` series tag, `DD MMM YY` expiry, slash-separated strikes, `CALL|PUT|CALL/PUT`, `@price` (sub-$1 renders `.95`), `TO OPEN/TO CLOSE`, bracket trees (`1st trgs seq`, `1st trgs OCO`).

**Canonical spine (pinned by the survey):**
```
ACTION signedQTY [SPREAD_TYPE] UNDERLYING 100 [(Weeklys)] DD MMM YY strike[/strike...] CALL|PUT|CALL/PUT @price [LMT] [TIF]
```
Anchored by one verbatim external citation: `SOLD -1 IRON CONDOR PINS 100 (Weeklys) 30 APR 21 77/87/77/67 CALL/PUT @6.57` (Simpler Trading, simplertrading.com/trading-education/tutorials/how-to-read-thinkorswim-trade-alerts). **Marked inferred, pending a TOS screenshot/copy-paste fixture pass:** `LMT`/TIF suffix placement, the butterfly 3-strike line format, vertical first-strike-follows-action rule, credit-on-BUY sign rendering, `TO OPEN` placement in the copyable string.

**Enterprise anchors:** zero TOS strings anywhere; adjacent machinery is schwab-py's strategy enum (`lib/schwab-py/schwab/orders/common.py:153-206`) and OCC symbology (`lib/schwab-py/schwab/orders/options.py:43-57`; `market/measurement/fly.py:27-35` `parse_occ`). Note the two-namespace fact: TOS paste string says `SPX 100 (Weeklys)`; Schwab/tape say OCC root `SPXW` (fixture `SPXW  260517C05790000`, `tests/market/fixtures/schwab_chain_spx.json:11`).

### 2.2 Mancini (level structure + FBD doctrine — the map)

**Role:** supplies the session's level ladder, regime read, and conditional plan grammar. Long-only ES futures; supplies **conditions, not orders** ("I have not had a single short in over a year", `email_2026-05-20_raw.txt:856`).

**Corpus:** 330 cleaned letters at `/root/projects/Strader/data/mancini-letters-clean/` (2025-06-24 → 2026-07-01) + raw letters in `Strader/mancini/archive/`; deepest distillation `COO/docs/research/2026-07-16-mancini-trigger-methodology.md` (co-tg7w). Parse is governed prompt-driven (`COO/conventions/mancini-parse-is-prompt-driven.md`); letters from Azure blob only (`COO/conventions/read-mancini-letters-from-blob-only.md`).

**Key entities/vocabulary:** setups — Failed Breakdown (~90% of trades), Level Reclaim, Back-Test Long, Breakdown Short; level language — support/resistance ladders with `(major)`, shelf, significant low (3 definitions, `email_2026-05-20_raw.txt:830`), range/pivot/zone, danger zone, bull flag; management — level-to-level with the 75%/next-level/10%-runner ladder (`email:806`), acceptance + non-acceptance protocol (`email:831-833`), knife-catch prohibition, profit protection mode, green-to-red rule, stop below lowest low; regime — Mode 1/Mode 2, the Golden Rule, elevator down + short squeeze "two siblings", bears/bulls control, lockout rally. Direction verbs already machine-listed at `mancini/parser.py:151-152`. Two parse generations: Gen-1 dataclasses (`Strader/mancini/parser.py`) and the production Gen-2 contract (`runbook/mancini/schema.py` — `LEVEL_KINDS=(support,resistance,pivot,target,trigger)`, `TRIGGER_TYPES=(price_cross,price_zone,time,regime,unconditional)`, verbatim-price guarantee in `validate.py`, deterministic cross-check `listlevels.py`). Payload v1 + level-state machine `untouched → tested/held → broken → reclaimed` per `docs/superpowers/specs/2026-07-25-mancini-stable-renderer-design.md` (st-3c4).

**Absent from corpus (do not model):** "Mr. Ranges" and "ledge" — zero grep hits across all 332 files.

### 2.3 Carmine (book-side triggers — the trigger)

**Role:** first-hour Bookmap order-flow trigger reads. Per the st-1s1 correction (authoritative): **levels conventional** (prior day H/L, range edges, balance-range landmarks — NOT profile LVNs), **triggers Bookmap/first-hour**.

**Corpus fact:** the enterprise holds **no primary Carmine material** — DReader `data/dreader.db` messages table has 0 rows; zero Carmine mentions in `/root/projects/DReader` or `COO/myDesk/trading/`. Everything on file is Steve's paraphrase or Strader synthesis.

**Key vocabulary:** exactly two verbatim terms — **"re-load"** ("resting orders getting eaten and reappearing at the same price") and **"zero print"** (definition explicitly pending harvest), both `Strader/knowledge/carmine-rosato-investitrade-lvn-method.md:18-20`; paraphrased Bookmap verbs stacking/pulling; method sequence mark level → impulsive departure → return → confirm with order flow. `CarmineSetup` Literal (`strader/entities/singleton.py:39-44`) mis-houses Mancini's setups (rename pending st-1s1); `mancini-carmine-confluence` tag (`conditions.yaml:72-75`, weight: high) carries a wrong operational definition, redefinition held for the Discord harvest. Order/entry grammar on file (`docs/playbooks/investitrade-playbooks-master-reference.md`, 773 lines: Aggressive/Conservative/Limit entries, ATR-unit stops 0.5–1.5, 0.5% risk) is **Steve-authored InvestiTrade-derived; fidelity to Carmine unverifiable**.

### 2.4 Strader code (the built middle)

**Role:** the numbers-side entity substrate the linguistic side must meet.

**Key entities:** data layer — `Instrument/Contract/Chain/Level/Session/ButterflyTemplate/ButterflyInstance/Position/Trade/Quote/BookEvent/Footprint*/VolumeProfile/TPO*/GexProfile` (`market/entities/`); signal layer — `Signal/Bias/Regime/Level/Alert/Action/InferenceRequest` (`market/signals/types.py`; `Action` is "recommendations, not executions", lines 38-40) and orderflow signals incl. `SetupRecognition` (`market/signals/orderflow.py:74-88`); recognition — `SetupRecognizer` four-stage machine, `Anchor`, `BeatFire/SetupInstance` with `BEAT_GLOSS` teaching strings (`market/orderflow/recognizer.py`, `anatomy.py:30-37`), parity-tested in CI; strategy — `SingletonSetup/SingletonPosition` (`strader/entities/singleton.py`), `Playbook/Vocabulary/PlaybookCatalog` (`strader/entities/playbook.py`), day classifier (`strader/evaluate/day_classifier.py`).

**Key vocabulary:** `conditions.yaml` controlled tags (machine-rejected if unknown, `playbook.py:189-194`); scenario codes S1–S6/F/T (`docs/drills/scenario-catalog.md`); "stages, not beats" display rule; establish-before-abbreviate; proto-grammar strings `center="ATM+5"`, `expiry="0DTE"` (`spread.py:9-13`) with **no parser**; delta-band strike tables prose-only in `strader/playbooks/singleton-directional.md`.

**Hard absences:** no Order/Ticket entity; no TOS syntax (only two prose mentions: `archive/DaysActivity-2026-05-17.md:18`, `runbook/datastream/__init__.py:3`); `broker_schwab/` read-only; no `[project.scripts]` CLI entry points; no spoken-intent parsing; three colliding `Level` types and two colliding `Bias` types (detailed in §7).

### 2.5 Spoken intent (input terminus)

**Role:** Steve's day-description in his own register — the parse target.

**Structure (consistent across the corpus, the natural parse target):** four tiers with a time-window overlay — (1) levels ladder (major/minor), (2) regime/bias keyed to a pivot ("Bears control below 7474, bulls above", `COO/myDesk/trading/mancini-latest-es-plan.md:7`), (3) opportunities as level-conditioned branches ("flush and recover 7412 → long"), (4) orders/positioning (vehicle, lot, scale, runner).

**Best raw specimen:** `/root/.mempalace-staging/strader/2026-07-13_10c153bc.md:1254` — Steve's verbatim outcome menu "Clean break, Clean reject, level retake, failed breakdown, failed trap, chop" and "I've lived (and lost lots) the flush that slices thru 20-30 points only to form the v-shaped recovery." Dictation texture is lowercase, typo-bearing ("thier", "posistions"), run-on — the normalizer must survive that noise. **No full-day raw dictation specimen exists.**

**Standing spoken-interaction artifacts (seven, all binding):** TTS-safe output (`feedback_mobile-spoken-style.md`), dictation-in/agent-keystrokes (`feedback_dictation-model.md`), establish-before-abbreviate (`knowledge/establish-before-abbreviate.md`), spell-out-references, stages-not-beats (`knowledge/stages-not-beats.md`), direction-inversion-watch (`knowledge/direction-inversion-watch.md` — "this is what scares me about me... keep an eye on me"), `no-autonomous-orders` (`intent.yaml:74-78`). Key vocabulary facts: "one level" ≈ 10 SPX points as a *distance unit* (`knowledge/directional-gex-butterflies.md`); v_down is the only V trade, v_up diagnostic (`knowledge/v-day-target-is-v-down-only.md`); zone dialects unified in `knowledge/zone-framework-equivalence.md`; corrections must persist same-turn (`feedback_corrections_persist_immediately.md`).

### 2.6 Constraints survey (governance overlay)

Not a vocabulary source; it fixes what the design may and may not do. Fully enumerated in §6.

---

## 3. The normalized entity model

**Two universal attributes first**, carried by every entity where applicable:

- **`frame: ES | SPX`** — no code carries a price frame today; Mancini and all orderflow reads are /ES points, execution is SPX strikes, conversion is the day's basis, checked once per session (`docs/foundation/08-es-spx-bridge.md`).
- **`provenance`** — two dimensions: *source tier* (canonical vendor-truth / community interpretation / measured — Steve's 2026-05-22 directive, `feedback_canonical-community-measured.md`) and *capture layer* (verbatim / Steve-recollection / Strader-synthesis — the Carmine survey's three-layer finding). Plus a *claim-status* for behavioral beliefs (verified / folklore / declined-to-formalize — e.g. trend-day reversion is UNVERIFIED per st-r1p; the 15-minute rule deliberately informal per `user_scalper_mentality.md`), required to honor `feedback_no-confabulation.md`.

**Namespace rule (st-1s1, non-negotiable):** Mancini and Carmine vocabularies stay distinct at the source layer. Both can *populate* a normalized Level or Trigger; the model never asserts that a Mancini level and a Carmine level are the same level. Confluence is a computed, provenance-labeled fact (a `day_context` tag), never a vocabulary merge.

### 3.1 Level

**Definition:** a price, or two-edge band, where prior decisions are stored; date-scoped and stateful.

**Attributes:** `price`, `price2` (zone edge, nullable), `frame` (ES|SPX), `kind` (support/resistance/pivot/target/trigger — Gen-2 `LEVEL_KINDS`, `schema.py:18`), `tier` (major/minor — Mancini's own annotation) plus enterprise-computed flags `key`/`conf` kept provenance-separate (renderer spec :38-39), `source` (mancini/manual/luxalgo/pac/gex/carmine-conventional/profile), `state` (untouched → tested/held → broken → reclaimed — renderer spec :52-56), `session_date`, `source_quote`.

| Source | Term(s) | Cite | Conflict / gap |
|---|---|---|---|
| Strader code | `market/entities/level.py:7` (price/label/source/annotation); signal `Level` (`market/signals/types.py:26`); `mancini/parser.py:29`; label-corpus `es_levels` floats | strader-code survey §8.1 | **Four Level representations to reconcile**; none carries `frame` or `state` |
| Mancini Gen-2 | `Level{price, kind, label, source_quote}` | `runbook/mancini/schema.py:23-41` | The strongest base; zone shorthand "7640-45" expands to edges (`listlevels.py:65-70`) |
| Mancini prose | support/resistance `(major)`, shelf, significant low, pivot, zone, danger zone, range floor | `email_2026-05-20_raw.txt:830,854,855` | "significant low" has 3 definitions; ranges "morph" (`email:792`) — identity is date-scoped |
| Carmine | prior day high/low, range edges, balance-range landmarks | st-1s1; `carmine-rosato-investitrade-lvn-method.md:18` | **NOT profile LVNs** — older repo framing under rework; contributes almost nothing new to level vocabulary |
| TOS | absolute strikes `6300/6320/6340` | tos-syntax survey §3.3 | Levels are analysis prices, strikes are execution prices; only chain resolution connects them |
| Spoken | "the level", "shelf", "big low", plus **distance unit**: "one level" ≈ 10 SPX pts | `directional-gex-butterflies.md`; spoken survey §4 | **Polysemy:** "dropped two levels" (distance) vs "lost the level" (price object) must parse differently |

**Zone dialects:** order block (ICT/SMC/LuxAlgo) = supply/demand base = Carmine LVN are "one event in four dialects" (`knowledge/zone-framework-equivalence.md`) — but the file's "real differences" paragraph (ICT expects a sweep first; Seiden's R/R filter) means the CLI accepts all four tokens as aliases into a Zone-flavored Level while retaining the spoken dialect in provenance; it does not flatten them losslessly.

### 3.2 Trigger

**Definition:** a condition that converts a level or commentary into action.

**Attributes:** `type` (price_cross/price_zone/time/regime/unconditional — Gen-2 `TRIGGER_TYPES`, `schema.py:19`), `anchor_prices[]` (+frame), `condition_text`, `namespace` (mancini / carmine-book / strader-stage), `evidence_instrument` (letter-doctrine / bookmap-depth / footprint-tape).

| Source | Term(s) | Cite | Conflict / gap |
|---|---|---|---|
| Mancini | acceptance, non-acceptance protocol (+5 pts, hold minutes), flush-and-recover, "7337 short trigger" | `email_2026-05-20_raw.txt:831-833,858` | Thresholds deliberately unquantified ("controlled grind" vs "knifing") — carry as qualifiers, don't compute |
| Carmine | re-load (defined), zero print (**undefined — pending-harvest**), stacking/pulling | `carmine-rosato-investitrade-lvn-method.md:18-20` | Mostly uncaptured; normalize to **book-side** events (MBP-1/st-9vl), not footprint, when tagged Carmine |
| Strader code | four-stage flush→stall→flip→confirm with named thresholds; `SetupRecognition.state` forming/confirmed/invalidated | `market/orderflow/recognizer.py:1-34`; `orderflow.py:74-88` | Explicitly Strader synthesis, "validated empirically, not experientially" (`recognizer.py:30-34`) — never present as Carmine's words |
| Spoken | "confirm" as entry trigger ("the prudent entry is triggered by the confirmation") | `2026-07-13_10c153bc.md:1254` | Display vocabulary is **stages**, never beats |
| TOS | — (no trigger concept in a single-line order; bracket trees carry trigger discipline) | tos-syntax §3.4 | — |

**Term collision to manage:** "trigger" is simultaneously a Level kind and a Commentary attribute (`schema.py:18-19`), and Mancini uses it as a price. The normalized model reserves **Trigger** for the condition entity and renders Mancini's "trigger" prices as Levels with `kind=trigger`.

### 3.3 Setup

**Definition:** a named, recognizable opportunity pattern at a level.

**Attributes:** `name`, `namespace` (mancini / strader-scenario / steve), `anchor: Level`, `direction`, `quality tier`, `state` (forming/confirmed/invalidated), `kind: setup | expression` — the distinction SGL demands and the entity model lacks (`singleton-directional.md`: "This is not a peer strategy"; pending COO decision).

| Source | Term(s) | Cite | Conflict / gap |
|---|---|---|---|
| Mancini | Failed Breakdown, Level Reclaim, Back-Test Long, Breakdown Short | trigger-methodology doc §2; `email:790,819,858` | FBD is at once a setup name, an event, and a level state (`reclaimed`) — disambiguate by entity class |
| Strader code | `CarmineSetup` Literal: failed_breakdown, level_reclaim, return_to_lvn, range_trap | `singleton.py:39-44` | **Mis-credited type name**; first two are Mancini's (provenance note :34-38, rename pending st-1s1) |
| Strader drills | scenario codes S1–S6 (S2 = failed breakdown, S3 = level reclaim), F/T series | `docs/drills/scenario-catalog.md` | Codes are optional aliases only — never bare (`establish-before-abbreviate.md`) |
| Spoken | outcome menu: clean break, clean reject, level retake, failed breakdown, failed trap, chop; V / v_down dump-and-return; knife-catch | `2026-07-13_10c153bc.md:1254`; `v-day-target-is-v-down-only.md`; `mancini-latest-es-plan.md:13` | v_up exists in detector schema but is **not a trade**; S2/S3 sibling split is family-level agreement at best ("Mancini himself re-labels between") |
| Carmine | (method sequence, not named setups) mark level → departure → return → confirm | `carmine-rosato-investitrade-lvn-method.md:14` | Paraphrase-layer provenance |
| TOS | — | | — |

### 3.4 Regime / DayType

**Definition:** the day's character and directional control, keyed where possible to a pivot level.

**Attributes:** `day_type`, `control` (bears/bulls + pivot Level), `bias`, `mode`, `day_context tags` (frozenset from `conditions.yaml`), per-tag `Provenance: objective|objective-baseline|subjective` (`day_classifier.py:114-123`).

| Source | Term(s) | Cite | Conflict / gap |
|---|---|---|---|
| Mancini | Mode 1 (trend, ~10%) / Mode 2 (range, ~90%), Golden Rule, bears/bulls control, lockout rally, chop, coiling | `email:801,812,855`; `mancini-latest-es-plan.md:7,12` | "Golden Rule" names two different rules (`email:801` vs :831) — qualify on use |
| Strader code | `Regime` signal (trending/ranging/volatile/compressed, `types.py:20-22`); day_context tags trend-up/down, range-chop, vol-*, gex-*, gap-*, etc. | `conditions.yaml`; strader-code survey §4.1 | **Bias collision:** `singleton.Bias` = Literal[bullish,bearish] (`singleton.py:29`) vs `signals.Bias` dataclass with neutral (`types.py:16`) — name + arity mismatch |
| Spoken | b-day / liquidation day, trend day, rotation day; D-shape vs P/b-shape profile | `session-briefing.md:30`; `2026-05-24_5a3bb221.md`; `feedback_corrections_persist_immediately.md` | The 7/23 "trend day"→"b-day" correction was lost four times — regime corrections must write through same-turn |
| Carmine / TOS | — | | — |

### 3.5 SessionWindow

**Definition:** a named time band binding behavior to the clock. **Binds to the trader profile, not the method** (Carmine survey §10.5).

**Attributes:** `name`, `start/end` (CT canonical), `owner_profile` (steve/carmine/mancini), `tz_provenance`.

| Source | Term(s) | Cite |
|---|---|---|
| Strader code | window-open 08:30–09:30 CT, window-midday, window-late 13:00–15:00 CT ("Steve's prime window") | `conditions.yaml:87-88` |
| Constraints | seven-stage trading day CT, Pre-market → Post-mortem | st-ze2; `COO/docs/superpowers/specs/2026-07-16-trading-day-stage-plan.md` |
| Mancini | trade window before 11am / after 3pm ET; avoid 11–2 | `email:851`; letters are ET, "subtract an hour" (trigger-methodology :5) |
| Carmine | first 2–3 hrs, out by 11:30; triggers first-hour | `carmine-rosato-investitrade-lvn-method.md:12`; st-1s1 |
| Spoken | first hour / 10:00–13:00 consolidation / 13:00–15:00 fly window / EOD | spoken survey §3 Windows |

**Conflict to preserve:** Carmine morning-only vs Steve window-late prime — never conflate.

### 3.6 Intent (conditional branch)

**Definition:** one if/then unit of the day plan: (level, condition, direction, quality, vehicle-hint). The CLI's core parse unit — Mancini states the target sentence form verbatim: "Professionals say 'If price tests X level, flushes it, and recovers, I long for a lvl to lvl move'… 'If price does none of the above, I do nothing'" (`email_2026-05-20_raw.txt:822`).

**Attributes:** `trigger: Trigger`, `direction` (+ **direction_anchor**: the flush direction, stated first — `direction-inversion-watch.md`), `setup: Setup`, `quality` ("high-quality long", "low win rate high R/R"), `window: SessionWindow`, `management_hint` (level-to-level, runner, fast cut), `claim_status`.

| Source | Term(s) | Cite |
|---|---|---|
| Mancini Gen-2 | `Commentary{text, trigger, tags, source_quote}` | `schema.py:70-89` — the closest existing entity |
| Mancini prose | bull case / bear case branches; bid direct; add on strength | `email:855-857`; `mancini-latest-es-plan.md:11-19` |
| Strader | approved regime-read if/then close: "rejection flush = V-down entry; push through 7564 = flies at risk" | `feedback_regime_read_commentary_style.md` |
| Spoken | "The flush and recovery of this is actionable; bonus if it tags 7398" | `mancini-latest-es-plan.md:11` |
| intent.yaml | **not** a trading-intent model — a zgent factory profile; contributes only governance (`no-autonomous-orders`) | `intent.yaml:74-78` |

### 3.7 StructureTemplate (vehicle)

**Definition:** pre-resolution order-structure intent — the vehicle and its relative geometry. **SPX only, always** (co-jferz); sizing pressure resolves via structure (strike/DTE/width), never instrument step-down.

**Attributes:** `vehicle` (fly / single / vertical / condor…), `center` (relative "ATM+5" or level-anchored "on the magnet" or absolute), `width` (points), `expiry` ("0DTE"/"1DTE"/ISO — needs the Weeklys/monthly calendar rule), `right`, `delta_band` (SGL tables: 0.60–0.70 morning, first-ITM ~0.7–0.9 late, <0.50 declared-lottery-only — prose only, `singleton-directional.md`), `lot_hint`.

| Source | Term(s) | Cite | Conflict / gap |
|---|---|---|---|
| Strader code | `ButterflyTemplate(center,width,expiry,contract_type)` — "ATM+5"/"0DTE" strings, **no parser** | `spread.py:9-13` | Proto-grammar, ad hoc; the CLI formalizes it |
| Strader playbooks | LDF late-day fly (center ~20 pts from flush low toward magnet, premium-is-the-stop); SGL singles | `late-day-butterfly.md`; `singleton-directional.md` | `kind: setup|expression` field missing |
| Spoken | fly / single, 3- or 5-lot, "centered on the magnet", 20-wide; "an option single is a futures contract on its last day" | `directional-gex-butterflies.md`; `singles-as-futures-proxy.md`; `buying-movement-delta-first.md` | .3Δ vs .6Δ open question (`user_scalper_mentality.md`) |
| TOS / schwab-py | `SpreadType` enum SINGLE/VERTICAL/BUTTERFLY/CONDOR/IRON_CONDOR/UNBALANCED_* | `common.py:153-206` | Only vertical + single-leg builders exist; no fly builder |
| Mancini / Carmine | — (Mancini supplies no order-structure vocabulary; Carmine's is Steve-authored InvestiTrade derivative) | mancini survey §6.10; carmine survey §6 | The whole vehicle layer is Steve's, not the sources' |

### 3.8 Order

**Definition:** one executable TOS line. **Entirely greenfield — no existing anchor type in the enterprise.**

**Attributes (from the TOS survey's entity table):** `action` (BUY/SELL), `quantity` (signed int — must agree with action), `spread_type`, `underlying` (SPX), `multiplier` (100), `series` (Weeklys/monthly — settlement-bearing, calendar rule not constant), `expiry`, `strikes[]` (absolute, ordering per spread type), `right`, `price` + `price_kind` (debit/credit) + tick rounding (SPX 0.05/0.10), `order_type` (LMT/MKT/STP — placement inferred), `tif` (inferred), `position_effect` (TO OPEN/TO CLOSE), and a **dual rendering**: TOS paste string + OCC symbols (`SPXW…`) per leg (`options.py:20-144` handles the OCC side).

### 3.9 Bracket

**Definition:** an order tree (entry + target/stop children) — TOS models it as `1st trgs seq` / `1st trgs OCO`, **not** a flat line (toslc.thinkorswim.com Order Entry docs; useThinkScript OCO thread). Steve's LDF doctrine (premium-is-the-stop + one-level profit trigger, `late-day-butterfly.md`) implies the CLI needs this beyond single lines. Whether v1 emits entry-only or a bracket script is an open question for Steve (§8).

### 3.10 Size / Risk

**Definition:** the sizing and rail set the CLI must check before emitting.

| Rule | Source |
|---|---|
| Max 2% per trade | `Strader/CLAUDE.md:195` |
| Escalate > $5,000 notional | `Strader/CLAUDE.md:69` |
| Structure is the sizing knob, not contract count | co-jferz "Live By SPX" (closed 2026-07-22) |
| Daily loss limit + per-strat budget + position-count cap — coming as code, required before 8/3 live | st-958 (P1, open), implementing co-59ky |
| Graduated go-live 2026-08-01, not full size | `knowledge/grow-into-live-trading.md` |
| Mancini management ladder: 75% first level up / more at next / 10% runner, trail | `email:806` |
| InvestiTrade: 0.5% account risk, ATR-unit stops 0.5–1.5 | `investitrade-playbooks-master-reference.md:92-116` — **Steve-authored, fidelity unverified** |
| SPX spread friction $0.10–0.30; slightly ITM for scalps | `Strader/CLAUDE.md:175` |

### 3.11 Position (management state)

**Definition:** a held position and its management verbs. Existing anchors: `Position` (fly-only, `market/entities/position.py`), `SingletonPosition` (`singleton.py:67-150` — target/stop in underlying points, r_multiple, "does not… route orders (that is Phase 4)"). Vocabulary: runner ("still holding the 10% runner from the 7506 Failed Breakdown", `mancini-latest-es-plan.md:20`), scale off risk, fast cut ("on the first wrong breath", `directional-gex-butterflies.md`), profit protection mode, green-to-red prohibition (`email:842`). Neither type models an *order to be placed* — Position and Order are distinct entities.

---

## 4. The pipeline

```
spoken day-description
  → capture (dictation-noise-tolerant)
  → parse into the four-tier structure (levels / regime / branches / positioning)
  → bind entities (Level+frame conversion, Regime tags, Setup, Window, Intent)
  → guards (direction-anchor echo; vocabulary establish-before-abbreviate; risk rails)
  → StructureTemplate
  → chain resolution (live snapshot → absolute strikes, net debit)   [mandatory stage]
  → Order (+ optional Bracket)
  → TOS string + OCC symbols, read back, emitted ONLY on explicit confirmation
  → Steve pastes into TOS. The CLI never routes.
```

Chain resolution is mandatory because Strader intent is relative ("ATM+5", "two levels off the flush low") while TOS strings are absolute strikes — `resolve_butterfly` + `Chain` already model it (`market/resolve.py:10-40`; net debit = mid(low) − 2·mid(center) + mid(high), same identity in `fly.py:7-8`). Chain snapshots can be internally time-skewed vs spot (~28 pt lag observed, st-096) — resolution needs same-instant capture or a staleness flag.

### Worked example — late-day SPX butterfly

**Spoken input (constructed from attested vocabulary; texture per the dictation specimens):**

> "b-day so far. morning flush found its low around ten thirty, we've been balancing since. mancini has sixty-four twelve as the major support, bears control below sixty-four seventy-four. consolidation is sitting around sixty-three twenty spx. if we get the late flush out of this range and it starts the v back, i want the fly on the consolidation, twenty wide, zero dte calls, two lots."

**Parse → entities:**
- **Regime:** b-day (morning low, afternoon balance — `session-briefing.md:30` pattern); control = bears below Level(6474, frame=ES, source=mancini, tier=major).
- **Levels:** Level(6412, ES, support, major, mancini). Frame conversion: today's basis (checked once per session, `08-es-spx-bridge.md`) applied; spoken "sixty-three twenty spx" → Level(6320, SPX, source=manual). The parser must resolve each spoken number's frame — ES for Mancini quotes, SPX for consolidation/strike talk (hazard §7.1).
- **Window:** window-late (13:00–15:00 CT, `conditions.yaml:87-88`) — LDF entry window 13:00 CT to close-minus-20 (`late-day-butterfly.md`).
- **Setup/Intent:** v_down dump-and-return (the only V trade, `v-day-target-is-v-down-only.md`); trigger = Trigger(type=price_zone, condition_text="late flush out of consolidation, V begins", namespace=steve). Entry is assumed on the drop — **no pre-drop classification gate** (`post-entry-tape-study.md:19-24`).
- **Guard — direction-anchor echo (mandatory):** CLI speaks back: *"Flush will be down, so the trap pays up — this fly is a long, calls, centered back at the consolidation. Correct?"* (`direction-inversion-watch.md`).
- **StructureTemplate:** ButterflyTemplate(center="6320" [consolidation magnet, per LDF pin-selection doctrine], width=20, expiry="0DTE", contract_type=CALL), lots=2.
- **Risk check:** est. debit 2 × $0.55 × 100 = $110 — under 2%/trade and $5k escalation; daily budget check deferred to st-958 code.

**Chain resolution (live snapshot):** strikes 6300/6320/6340; net_debit = mid(6300C) − 2·mid(6320C) + mid(6340C) = 0.55.

**Emitted TOS string** (format per §2.1 spine; **line format for the 3-strike butterfly is inferred, pending fixture verification** — tos-syntax survey §3.5):

```
BUY +2 BUTTERFLY SPX 100 (Weeklys) 25 JUL 26 6300/6320/6340 CALL @.55 LMT
```

Plus OCC legs for cross-checking: `SPXW  260725C06300000`, `SPXW  260725C06320000` (×2), `SPXW  260725C06340000`.

**Read-back and stop:** *"Buying two SPX flies, calls, sixty-three hundred, sixty-three twenty, sixty-three forty, expiring today, fifty-five cents debit — one hundred ten dollars total, and the premium is the stop. Say go to emit."* Management doctrine attaches as advisory text (not a second order line in v1): profit trigger at ~one-level (~10 SPX pts) reversion, runner to the pin (`directional-gex-butterflies.md`; `late-day-butterfly.md`).

---

## 5. CLI grammar sketch

Design constraints from the spoken-intent survey: plain names, no bare codes in or out (`establish-before-abbreviate.md`); conversational-grade, not flag-soup (`terminal-ux-novice.md`); TTS-safe read-back — answer first, short sentences, spoken-friendly numbers (`feedback_mobile-spoken-style.md`); robust to lowercase/typo/run-on dictation; corrections write through same turn (`feedback_corrections_persist_immediately.md`); display "stages", bind to beat-named fields (`stages-not-beats.md`).

**Candidate command shapes (small verb set, each accepting free dictation after the verb):**

- `read <free dictation>` — ingest the day description; CLI answers with the four-tier structured read-back (ladder, regime sentence keyed to a pivot, branch list, positioning) in the approved regime-read format (`feedback_regime_read_commentary_style.md`).
- `mark <level talk>` — add/adjust levels: "mark sixty-four twelve major support, mancini" → Level with frame resolved and echoed ("that's ES; SPX equivalent about sixty-three sixty at today's basis").
- `call <regime talk>` — set/correct day type and control: "call it a b-day" / "bears control below sixty-four seventy-four".
- `arm <branch talk>` — register an Intent: "arm the failed breakdown at sixty-four twelve, long on the reclaim". CLI echoes the direction anchor before accepting.
- `fly <structure talk>` / `single <structure talk>` — StructureTemplate: "fly on the magnet, twenty wide, zero dte, two lots" / "single, first strike in the money, calls".
- `price` — run chain resolution, speak the debit and breakevens.
- `go` / `stand down` — the explicit-confirmation terminus; only `go` after a full read-back emits the TOS string (and never routes).

**Alias policy:** scenario codes (S2 etc.) accepted as input aliases but always expanded on output ("S2, the failed breakdown"); the four zone-dialect tokens (order block / LVN / FVG / supply-demand base) accepted as aliases into Zone-Level with dialect retained in provenance.

**Number handling:** spoken prices arrive as "sixty-four twelve" or "seventy-four seventy-four"; the parser resolves frame by context (Mancini attribution → ES; strike/consolidation talk → SPX) and **always echoes the resolved frame** — the survey flags "seventy-four twelve" as genuinely ambiguous between frames.

This is a sketch, not a spec — the surveys note that no full-day dictation specimen exists to validate any grammar against (§8, coverage).

---

## 6. Constraints the design must respect

1. **No autonomous orders, structurally enforced.** Terminus is a paste-string. `no-autonomous-orders` (`Strader/.claude/rules/no-autonomous-orders.md`; `intent.yaml:74-78`); schwab-py fork hobbled — order/account methods physically removed, DEFENSE NOTE `lib/schwab-py/schwab/client/base.py:16` (st-nz4); permissions gate `.claude/rules/schwab-api-gate.md`, violations policed (st-xor). `Action` signals are recommendations (`types.py:38-40`).
2. **SPX only — closed decision, never re-propose XSP/SPY.** co-jferz "Live By SPX" (2026-07-22); `project_spx-only-overrule.md`. Sizing via structure.
3. **No pre-drop filtering for butterflies.** Entry on every late-day drop is assumed; build post-entry recognition, never entry-blocking gates. `docs/measurement/post-entry-tape-study.md:19-24`; `leg-profiler-findings.md:110-111`; `feedback_strader-no-predrop-filter.md`.
4. **Harness-first.** Normalization/parse paths deterministic code; LLM only as a bounded function for genuine free-text interpretation. st-ze2; `COO/docs/superpowers/specs/2026-07-16-trading-day-stage-plan.md:13`; `feedback_harness-first-migration.md`.
5. **Risk rails:** 2%/trade (`CLAUDE.md:195`), >$5,000 escalation (`CLAUDE.md:69`), daily loss limit/sizing budget landing as code before 8/3 (st-958, P1); graduated go-live 2026-08-01 (`knowledge/grow-into-live-trading.md`).
6. **Direction-inversion guard is mandatory.** Echo the direction anchor before accepting directional intent. `knowledge/direction-inversion-watch.md`.
7. **Data-feed realities:** Schwab-first (st-096, 7-day refresh-token wall, heartbeat st-e2f); one streaming session per account conflicts with Steve's live ToS session — prefer REST polling; GexBot paused — never cite live GEX (`project_gexbot_paused.md`, `project_gexbot-paused-orderflow-focus.md`); TradingView MCP dead, screenshots only (`knowledge/tradingview-screenshot-pipeline.md` — CLAUDE.md:260 is stale); Mancini letters from Azure blob only, parse prompt-driven (`feedback_mancini-read-from-blob-only`-equivalent conventions in COO).
8. **Vocabulary provenance is load-bearing:** st-1s1 correction (Carmine levels conventional / triggers Bookmap first-hour); canonical/community/measured tiers per term (`feedback_canonical-community-measured.md`); no confabulation — every numeric claim cited (`feedback_no-confabulation.md`); verify rule currency before market-structure claims (PDT incident, `feedback_verify-rule-currency-first.md`).
9. **Spoken-interaction law:** TTS-safe output; dictation-in/agent-keystrokes; establish-before-abbreviate; stages-not-beats; no "gated" jargon (`feedback_avoid-gated-jargon`); corrections persist same-turn. All cited in §2.5.
10. **Timing canon:** all session timing CT (`Strader/CLAUDE.md:255`); seven-stage day (st-ze2); cron layer flagged ET-shaped needing CT reconciliation before automation hangs off it (st-ze2 note).
11. **Entity composition, not duplication:** the CLI's entities compose with the existing playbook/singleton/recognizer entities (constraints survey §3); Strader owns domain authority, COO structural authority (`Strader/CLAUDE.md` §Division of Labor). No silent metered data pulls (st-9vl, st-ve6 spend-approval pattern).
12. **Deliverables rendered, not file paths** (`shared-executable-space` rules; st-79z.1 AC).

---

## 7. Normalization hazards

Where the sources genuinely conflict or resist unification, with survey evidence:

1. **ES vs SPX price frames.** Mancini and all orderflow reads are /ES; execution is SPX strikes; basis drifts and shifts at contract roll (`docs/foundation/08-es-spx-bridge.md`; `email:795,798`). No code carries a frame attribute today. Spoken numbers are frame-ambiguous.
2. **"Level" polysemy.** Price object vs distance unit (≈10 SPX pts, `directional-gex-butterflies.md`). "Dropped two levels" ≠ "lost the level".
3. **Three-plus `Level` types and two colliding `Bias` types in code.** `market/entities/level.py:7` / `market/signals/types.py:26` / `mancini/parser.py:29` / Gen-2 `schema.py:23` (+ label-corpus floats); `singleton.Bias` Literal[bullish,bearish] vs `signals.Bias` with neutral (`types.py:16`) — name collision plus arity mismatch.
4. **Mancini/Carmine namespace separation (st-1s1).** `CarmineSetup` names Mancini's setups; `mancini-carmine-confluence` (highest-weight tag) carries a wrong operational definition ("within 2 ES pts of a profile LVN" mischaracterizes Carmine). Any model importing these names as-is inherits the error. Levels and triggers must be distinct entity classes — the prior conflation happened exactly because "level" and "zone" were interchangeable (carmine survey §10.1-2).
5. **Term collisions:** "Golden Rule" ×2 (`email:801` vs :831); "trigger" as Level kind / Commentary attribute / Mancini price (`schema.py:18-19`); "Failed Breakdown" as setup, event, and level state (renderer spec :56).
6. **Zone dialects don't flatten losslessly.** Four dialects, one event, real edge-case differences (`zone-framework-equivalence.md`).
7. **Level identity is date-scoped and stateful.** Ranges morph (`email:792`); supports flip to resistance when broken (renderer spec :55).
8. **Timing conflict:** Carmine first-hour/out-by-11:30 vs Steve's window-late prime (`conditions.yaml:87-88`) — session windows bind to trader profile.
9. **Display vs code vocabulary fork:** speak "stages", bind `beats` fields (`stages-not-beats.md`; `anatomy.py:30-37`).
10. **Aggressor-side naming inversion:** Databento side B=buy/A=sell (`trade.py:13-16`) vs footprint `ask_vol`=buy-aggressor (`footprint.py:13-17`) — the language layer must not leak it.
11. **Timezone split:** code CT, Mancini ET, spoken arbitrary (`trade.py:18`; `mancini/parser.py:13`; trigger-methodology :5).
12. **Boilerplate vs day-signal:** ~95% of each letter is repeated doctrine (~314-316 of 330 letters, trigger-methodology §3); Gen-2 prompt already excludes recap (`llm.py:140`).
13. **Deliberately unquantified perception thresholds:** "controlled grind" vs "knifing", acceptance duration — carry as qualifiers, cannot be computed (trigger-methodology §4).
14. **Direction synonym cloud:** rip/squeeze/rally/pop vs flush/knife/elevator/sweep — Gen-1's word-count normalizer (`parser.py:148-159`) is insufficient; needs polarity + intensity mapping.
15. **Provenance tier flags differ:** `major` is Mancini's; `key`/`conf` are enterprise-computed (renderer spec :38-39) — keep separate.
16. **Asymmetries that look symmetric:** v_up is not a trade (`v-day-target-is-v-down-only.md`); S2/S3 split achieves family-level agreement only (scenario-catalog.md S3).
17. **Beliefs vs measurements:** trend-day reversion UNVERIFIED (st-r1p); 15-minute rule deliberately informal — claim-status attribute required.
18. **Two symbol namespaces:** TOS `SPX 100 (Weeklys)` vs OCC `SPXW  …` — emit both; redundant action/quantity-sign fields must agree; `(Weeklys)` is settlement-bearing (calendar rule, not constant).
19. **Brackets don't flatten:** the single-line protocol covers one order; LDF's premium-is-the-stop + profit trigger implies a `1st trgs seq` tree.
20. **Inferred TOS grammar elements** (§2.1) rest on one verbatim iron-condor citation plus in-enterprise pricing identities — fixture verification is the cheapest de-risk.
21. **Undefined Carmine terms:** "zero print" has no definition, "re-load" one line — mark `pending-harvest`, never guess; freezing Carmine vocabulary now risks encoding the retracted version (spoken survey §9.4).
22. **CM discrepancy (COO-facing, flagged by spoken survey §7):** CM unified search returned non-null semantic scores (0.539/0.631) on 2026-07-25, contradicting `remember-via-cm.md`'s verified-2026-07-19 claim that the semantic leg is dead — worth a bead, unresolved here.

---

## 8. Open questions for Steve

1. **TOS fixture pass:** open TOS, build each shape (single, vertical, butterfly, condor, bracket), copy the confirm-dialog text verbatim into a fixtures file — five minutes of screen time converts every "inferred" grammar element to "certain" (tos-syntax survey §3.5).
2. **Entry-only line or bracket script?** Does the CLI emit one entry line (manage manually per doctrine) or a `1st trgs seq` bracket representation for premium-is-the-stop + profit target?
3. **Playbook `kind: setup | expression` field** — the pending COO decision `singleton-directional.md` names; the entity model needs it first-class.
4. **Spoken-number frame default:** when a bare price is dictated with no attribution, default frame ES or SPX? And confirm the frame-echo behavior isn't too chatty.
5. **Default lot and delta band** when unspecified: 3- vs 5-lot; .3Δ vs .6Δ singles question (`user_scalper_mentality.md`).
6. **Record one full-day raw dictation** ("here's my read of today", end to end) — the single most valuable missing specimen before grammar design (spoken survey §9.8).
7. **Carmine vocabulary freeze vs wait:** proceed with the two-term + pending-harvest namespace now, or hold trigger-grammar work for the Discord harvest st-1s1 depends on?
8. **Debit/credit sign convention** in the emitted string (does a net-credit BUY render `@-x.xx`?) — partly answerable by the fixture pass, partly preference.
9. **Should the CLI emit OCC symbols alongside the TOS string** (useful for cross-checks against Schwab/tape) or keep output to the one paste line?
10. **CarmineSetup rename timing** (st-1s1) — the CLI can adopt corrected names from day one; confirm the target naming so code and CLI don't fork.

---

## 9. Coverage — gaps and survey limits (recorded honestly)

- **No primary Carmine corpus exists anywhere in the enterprise.** DReader `data/dreader.db` messages: 0 rows; harvest not landed; cannot confirm the anonymized Discord channels include InvestiTrade. "Zero print" undefined. The InvestiTrade master reference is Steve-authored with no source citations — fidelity unverifiable.
- **No TOS order string, generator, or specimen exists in the enterprise** (three independent grep passes across Strader, COO/myDesk, and memories). External canon rests on one verbatim iron-condor line; the butterfly 3-strike format specifically has **no external verbatim** — it is reconstructed.
- **No full-day raw dictation specimen exists**; the spoken corpus is fragments plus Strader-authored formats Steve approved.
- **"Mr. Ranges" and "ledge": zero hits** in 332 corpus files — not modeled, per the survey's instruction.
- **~20 Strader beads** (st-e56, st-vrs, st-2f2, st-cm5, st-7h9, st-gsh, st-9lh, st-x1o, st-aeg, st-qen, st-m40, st-r3f, st-5n8, st-qj0, st-6mo, st-5pg, st-ka2, st-xb2, st-85b, st-q2d) show only "task" in list output and were not individually `bd show`n by the constraints survey — an exhaustive pass was not done.
- **SPX-only decision (co-jferz) has not graduated into Strader's knowledge bundle** — binding via the epic and COO records regardless.
- **Stale docs flagged, not fixed:** `Strader/CLAUDE.md:260` (TradingView MCP "primary") and the pre-st-nd5 three-strategy framing; knowledge/ + beads outrank CLAUDE.md where they conflict.
- **CM semantic-leg discrepancy** (hazard #22) observed but not resolved; the spoken survey recommends a bead.
- The worked example's spoken input (§4) is **constructed** from attested vocabulary, not a recorded utterance — a real specimen should replace it before grammar validation.
