# Execution engine — operations manual

**Reader: Desk.** This is a reference for an agent that has to hold the engine in
context and then design against it, operate it, or answer questions about it
without guessing. It is therefore complete rather than readable: every entry
point with its real arguments, every bound with its real condition, every event
with its real field names. Steve's short version of the same ground is
`myDesk/reports/2026-08-30-execution-engine-operations-guide.md` in the COO repo
(on his desk under **Trading**); that one is written to be read aloud, this one
is written to be relied on.

**Provenance.** Everything below was read from the source or measured on
2026-08-30 between 13:45 and 14:30 CT, on branch `main` of
`/root/projects/Strader`. Where a fact is a design intent rather than code, it
says so. Where a docstring in the tree disagrees with the code, this document
follows the code and records the disagreement in §12.

**Version.** The engine's operator surface as described here is **v0.7**
(Steve's framing, 2026-08-30). The roadmap to v1 is
`docs/plans/2026-08-30-execution-engine-cli-v1-roadmap.md`.

---

## 1. What the engine is

Five parts. Three of them are code you can run today; one is built but has never
been launched; one is the credential lifecycle that all of them depend on.

| Part | Package | State | Can it transmit an order? |
|---|---|---|---|
| **Intent desk** — speak the day, get a paste line | `strader/intent/` | works | No. Ends at the clipboard. |
| **FD0** — budget-derived stop, exit block, attempt ledger | `strader/execution/` | works, as a library | No. Renders text. |
| **execd** — the live execution service | `execd/` | stage 1 of 5, mock broker only | **Not yet.** No transport in the package. |
| **Fire server** — ARM → FIRE page on the tailnet | `scripts/fire_server.py` | built, never launched, dry run | No. Journals `transmitted: false`. |
| **Schwab read feed + token** | `strader/execution/feed.py`, `broker_schwab/`, `scripts/refresh_schwab_token.py` | works, read-only | No. Order calls are removed from the library. |

The two halves that matter for design do not yet meet: the intent desk produces
a **paste string** for Steve's hands; execd consumes an **OrderIntent JSON** over
a loopback API. Joining them is stage 5 of the execd epic (`st-47i2`). Nothing in
the tree does it today.

## 2. Every entry point, complete

There is **no console script**. `pyproject.toml` has no `[project.scripts]`
table (checked 2026-08-30), so nothing installs a `strader` command; everything
is `python -m` or a path to a script. There are exactly two `__main__.py` files
in the repo outside `.venv` and `lib`.

| Command | Kind | What it is |
|---|---|---|
| `python -m strader.intent` | interactive REPL | The intent desk. §3. |
| `python -m execd --mock …` | long-running server | execd. Its operator surface is HTTP, not argv. §5. |
| `python -m strader.execution.feed --preflight --token PATH` | one-shot check | Go/no-go preflight. §6. |
| `python scripts/fire_server.py [--port N]` | long-running server | Fire server. §7. |
| `python scripts/refresh_schwab_token.py` | interactive chore | Weekly re-auth. Takes no arguments; has no `--help`. §6. |
| `python scripts/schwab_token_health.py --no-bead --no-push` | one-shot check | Token staleness. Exit 0 healthy, 1 action needed. §6. |

All of these are run through the repo venv: `/root/projects/Strader/.venv/bin/python`.
`pyproject.toml` puts the repo root on `sys.path` for both the package and the
carried infra (`strader*`, `market*`, `broker_schwab*`, `runbook*`), so a
`PYTHONPATH=.` prefix is no longer required and any surviving instance of it is
vestigial.

FD0 has **no command line of its own**. It is a library the intent desk calls.

---

## 3. The intent desk — `python -m strader.intent`

Source: `strader/intent/cli.py` (entry), `session.py` (verbs), `grammar.py`
(parsing), `entities.py` (data model), `readback.py`, `tos.py`, `numbers.py`,
`bracket.py`, `replay.py`.

### 3.1 Flags

| Flag | Default | Effect |
|---|---|---|
| `--once TEXT` | — | Handle one line, print the read-back, exit 0. |
| `--speak` | off | Read-backs rendered for the ear: prices spoken, no abbreviations. |
| `--chain FILE.json` | — | Loads a chain snapshot. **Without it `price` cannot run** and answers `No chain loaded — start with --chain FILE.json to price.` A missing file exits 2. |
| `--day YYYY-MM-DD` | today, Central | Which day's plan to open. |
| `--plan-dir DIR` | `data/intent` (repo-relative) | Where the day's plan JSON lives. |
| `-v`, `--verbose` | off | `logging` at INFO instead of WARNING. |

Exit codes: `0` normal (including EOF and Ctrl-C), `2` the `--chain` file does
not exist.

### 3.2 The chain snapshot format

`--chain` takes a JSON object; `load_chain` (`cli.py:33`) reads it:

```json
{"underlying": "SPX", "underlying_price": 6320.5, "expiry": "2026-08-22",
 "calls": [{"strike": 6300, "bid": 8.1, "ask": 8.4, "delta": 0.62}],
 "puts":  [{"strike": 6300, "bid": 7.9, "ask": 8.2, "delta": -0.38}]}
```

Required per row: `strike`, `bid`, `ask`. Optional: `symbol` (synthesised as
`SPXW{yymmdd}{C|P}{strike*1000:08d}` when absent), `last` (defaults to mid),
`volume`, `open_interest`, `delta`, `gamma`, `theta`, `vega`,
`implied_volatility` — all greeks default to `0.0`. Required at the top level:
`expiry` (ISO date), `underlying_price`. `underlying` defaults to `"SPX"`.

**There is no live chain snapshot producer wired to this flag.** `price` reads a
hand-made file. That is a named gap, not an oversight.

### 3.3 The verbs

Dispatch is `Session.handle` (`session.py:106`). The first whitespace-delimited
word, lowercased with trailing `:` and `,` stripped, is matched against the verb
table. **An unrecognised first word means the whole line is passed to `read`** —
that is what makes free dictation work. `stand down` is matched on the whole
line before the split, because it is two words.

| Verb | Argument | Returns | Side effects |
|---|---|---|---|
| `read` | free text | full read-back | absorbs levels, regime, structures, unparsed; stages the last intent found |
| `mark` | free text | full read-back | adds levels; on failure appends to `unparsed` and answers `No level in: "…". Say the price and what it is — support, resistance, pivot, target.` |
| `call` | free text | full read-back | merges the regime; on failure `No day type or control in: "…".` |
| `arm` | free text | the direction-anchor echo | **stages** an intent as `pending`; never confirms it |
| `yes` | — | full read-back | confirms the pending intent, appends to `plan.intents` |
| `no` | — | `Dropped. Say it again with the flush direction first if you want it.` | clears pending |
| `fly` | free text | full read-back | appends a `StructureTemplate` with `vehicle="fly"` |
| `single` | free text | full read-back | appends a `StructureTemplate` with `vehicle="single"` |
| `price` | — | order line + paste line + FD0 block | resolves the **last** structure against the loaded chain; sets `plan.orders` and `plan.bracket` |
| `go` | — | the staged paste line and legs | writes `data/intent/staged/<stamp>-<shape>.json`; **sends nothing** |
| `stand down` | — | `Standing down. Nothing priced, nothing pending.` | clears orders, bracket and pending |
| `show` | — | full read-back | none beyond rendering |
| `frame` | `es` \| `spx` | `Bare prices are ES from here on.` | sets `plan.frame_default`; anything else answers `Frame is ES or SPX.` |
| `basis` | a number | `Basis 92: an ES price less 92 is the SPX price.` | sets `plan.basis` (ES minus SPX, in points) |
| `replay` | free text | region emissions, one line each | logs only; touches nothing else on the plan |
| `quit` / `exit` | — | — | leaves the REPL (handled in `cli.py`, not `Session`) |

`VERBS` is declared at `session.py:37`. Note `quit`/`exit` are **not** in it —
they are handled by the REPL loop, so `session.handle("quit")` would be read as
dictation. That matters for any caller driving `Session` directly.

### 3.4 The three refusals worth knowing

1. **`arm` never arms.** It stages and returns the anchor echo. Only `yes`
   confirms. This is deliberate (`session.py:196-207`).
2. **A stale pending is refused.** `PENDING_MAX_MINUTES = 10`. `yes` on an
   intent staged more than ten minutes ago clears it and answers
   `That was staged N minutes ago and the tape has moved. Say it again if you
   still want it.`
3. **`go` refuses while anything is unconfirmed.** If `plan.pending` is set, or
   any intent in `plan.intents` has `confirmed=False`, `go` answers `An intent
   is waiting for a yes or no. Answer it before go.` With nothing priced it
   answers `Nothing priced. Say price first.`

### 3.5 The direction-anchor check

`Intent.expected_direction` and `Intent.looks_inverted` (`entities.py:134-149`)
compare the direction Steve said against what the setup family implies, given
which way the first move went. `SETUP_FAMILY` (`entities.py:42`) classes nine
setups: `failed_breakdown`, `level_reclaim`, `flush_and_recover`, `v_down`,
`failed_breakout`, `level_reject`, `clean_reject` are **trap**; `clean_break`
and `breakdown_short` are **continuation**. A trap pays against the first move,
a continuation with it. When they disagree the echo says `INVERTED` and asks
again — it is a check, not a refusal, and `yes` keeps the intent exactly as
said.

### 3.6 What `price` does

`Session.price` (`session.py:273`) resolves `plan.structures[-1]`:

- **`fly`** — needs a `width` (`a fly needs a width — say 'twenty wide'`).
  Resolves a `ButterflyTemplate` through `market.resolve.resolve_butterfly`.
  Price is `inst.net_debit` rounded to 2dp; `est_cost_usd = debit * 100 * lots`.
- **`single`** — `delta_hint == "first-ITM"` picks the nearest in-the-money
  strike (calls below spot, puts above); otherwise the nearest strike to spot.
  Price is `contract.ask` rounded to 2dp — a marketable limit, the same choice
  FD0 makes. `est_cost_usd = ask * 100 * lots`.
- Anything else raises `{vehicle} pricing is not built yet`. **`vertical` and
  `condor` are in the `Vehicle` type but have no pricing path.**

Centre resolution (`_center_spec`, `session.py:347`): `ATM` or `ATM+N` passes
through; a bare number passes through; a **label** is looked up against the
plan's levels by `label` or `kind`, falling back to the last `target` or `pivot`
level, and raising `no level on the plan called '<c>' — mark it first` if
neither exists. An ES-framed price with no basis raises `<price> is an ES price
and no basis is set — say 'basis <points>'`.

### 3.7 The FD0 bracket attached at price time

`_bracket_for` (`session.py:293`) calls `strader.intent.bracket.bracket()` and
stores `Ticket.to_dict()` on `plan.bracket`. Two non-fatal outcomes:

- `NotBracketable` — anything defined-risk. A butterfly's loss is its debit, so
  there is no stop to add. Logged, no note shown.
- `CannotFund` — FD0 could not fund a stop inside the budget. Shown to the
  operator as `FD0 could not fund a stop: <reason>`.

When a bracket exists, the read-back appends
`FD0 stop (budget-derived, $100 / 2 attempts):` followed by
`Fd0.render_stop(t)`, a blank line, and `Fd0.render_exit(t)`.

### 3.8 The paste line

`strader/intent/tos.py`. One line, no indent, no trailing newline — the paste
breaks on stray whitespace.

- Single leg: `BUY +1 SPX 100 (Weeklys) 22 AUG 26 6300 CALL @8.40 LMT`
- Multi leg: the same with the spread keyword after the signed quantity —
  `BUY +1 BUTTERFLY SPX 100 (Weeklys) 22 AUG 26 6280/6300/6320 CALL @1.25 LMT`
- Expiry format `tos_expiry`: day unpadded, month as three upper-case letters,
  two-digit year.
- Price format `tos_price`: `.55` under a dollar, `1.25` above.

`render(order)` returns `(string, status)` where status is `verified` when
`tests/fixtures/tos/<shape>.txt` exists and `inferred` when it does not. The
shape files are `single.txt`, `vertical.txt`, `butterfly.txt`, `condor.txt`.
**The fixture directory does not exist**, so every shape renders as `inferred`
today — including the single, whose shape is actually confirmed from FD0's
2026-08-03 research. Steve owes the confirm text (`st-79z.5`).

`occ_symbols(order)` returns one OCC symbol per leg, root padded to six with
spaces: `SPXW  260822C06300000`. A butterfly's centre leg appears **twice**,
because it is held twice.

### 3.9 Files the intent desk writes

| Path | When | Contents |
|---|---|---|
| `data/intent/<YYYY-MM-DD>.json` | after **every** verb | the whole `DayPlan` |
| `data/intent/staged/<YYYYMMDDTHHMMSS>-<shape>.json` | on `go` | `staged_at`, `order`, `tos`, `tos_status`, `occ`, `plan`, and `fd0` when a bracket exists |

The plan is written through a `.partial` temporary and renamed, so a crash
mid-write cannot truncate it (`entities.py:218`). A save failure is logged at
ERROR and swallowed — the session continues (`session.py:58`).

The `fd0` block on a staged record holds `stop_trigger_spx`, `exit_fields`,
`max_loss_usd`, and `derivation.as_record()`.

**`data/intent/` does not exist yet.** The desk has never been run for real.

### 3.10 The `DayPlan` shape

`entities.py:190`. Fields: `date`, `frame_default` (`"ES"` default), `basis`,
`levels[]`, `regime`, `intents[]`, `structures[]`, `orders[]`, `unparsed[]`,
`log[]`, `pending`, `pending_at`, `bracket`.

Types worth naming for a caller: `Price(value, frame, said)`;
`Level(price, kind, tier, source, label, price2, state, quote)` where `kind`
must be in `runbook.mancini.schema.LEVEL_KINDS` and `source` is one of
`mancini | carmine | manual | profile | gex | luxalgo`;
`Trigger(type, anchors[], condition_text, namespace)` where `type` must be in
`TRIGGER_TYPES`; `Setup(name, namespace, anchor, quality, state)`;
`Regime(day_type, control, pivot, bias, tags[], quote)`;
`StructureTemplate(vehicle, center, width, expiry, right, lots, delta_hint, quote)`;
`Order(action, quantity, spread_type, expiry, strikes, right, price, price_kind,
underlying, multiplier, series, order_type, tif, position_effect, est_cost_usd)`.

`Order.__post_init__` enforces that `action == "BUY"` agrees with
`quantity > 0`; a mismatch raises.

`WINDOWS` (`entities.py:33`) names three Central session windows:
`window-open` 08:30–09:30, `window-midday` 09:30–13:00, `window-late` 13:00–15:00.

Mancini's and Carmine's vocabularies are **separate namespaces**. Nothing in
this model ever asserts that two sources' levels are the same level.

---

## 4. FD0 — `strader/execution/`

A library. No command line, no credentials, no order API. It renders a ticket
and an order string; Steve pastes it.

### 4.1 The state machine

`strader/execution/fd0.py`. States: `IDLE`, `COMPOSED`, `OPEN`, `CUT_PRESUMED`,
`WAITING`, `DONE`.

```
IDLE ──s──▶ COMPOSED ──in <px>──▶ OPEN ──── out <px> (his own cut) ──┐
  ▲            │ n                  │ tape through the stop trigger  │
  └────────────┘                    ▼                                ▼
                          CUT_PRESUMED ──out <px>──▶ WAITING ──s──▶ COMPOSED
DONE ◀── x ── from any state
```

An illegal key raises `IllegalTransition` rather than being ignored — a
silently swallowed keystroke on an execution surface is indistinguishable from
a stuck terminal.

### 4.2 The API

`Fd0.compose(chain, spx_now, **kw) -> Ticket` · `.discard()` ·
`.confirm_fill(premium_pts, now=None) -> Attempt` ·
`.observe(spx, now=None) -> bool` ·
`.confirm_exit(premium_pts, now=None) -> Attempt` · `.end()` ·
`.save()` / `Fd0.load(state_path, …)` · `.status_line()` ·
`.render(ticket, clipboard=False)` · `Fd0.render_stop(ticket)` ·
`Fd0.render_exit(ticket)` · `.budget` (property).

Module functions: `checklist(...)`, `journal_path_for(day, root)`,
`state_path_for(day, root)`. Exceptions: `IllegalTransition`, and from
`compose`: `CannotFund`, `NoStrikeInBand`.

Re-exported from `strader.execution`: `Budget`, `CannotFund`, `Contract`,
`Derivation`, `NoStrikeInBand`, `Ticket`, `compose`, `derive`,
`noise_floor_spx`, `order_string`, `parse_chain`, `pick_strike`,
`template_fields`.

### 4.3 Two guarantees, both about not acting

- **It never transmits.** No order API, no credentials. The stop lives on
  Schwab's side once Steve sends it, conditioned on the SPX tape, so the harness
  watching the tape is bookkeeping only — the broker owns the exit.
- **It never re-enters.** `observe()` can move the machine to `CUT_PRESUMED`
  and can refuse a compose, but no path in the file opens a position. Reload is
  Steve pressing the key again. "Cut and wait" counters the chasing instinct
  rather than automating it.

### 4.4 The attempt ledger

A list of attempts, not a running total, so the tape estimate booked at
presumption can be **corrected** by Steve's confirmed exit without
double-debiting the budget. `Attempt.realized_usd` is **positive for a loss**;
`Attempt.estimated` marks a loss booked from the tape rather than from a
confirmed fill.

Since 2026-08-23 the machine saves itself after every transition, because the
dictation pane runs one line per process and `in 1.25` has to find what `go`
composed. `out` is legal straight from `OPEN` — Steve's own word that he is out
beats a presumption the tape never made.

---

## 5. execd — the live execution service

Source: `execd/`, 2,631 lines across 11 modules. Tests: `tests/execd/`,
**365 passing in 4.58s**, measured 2026-08-30 14:0x CT
(`api 49 · arming 21 · bounds 66 · intent 25 · journal 23 · service 76 ·
stops 23 · vault 44 · wall 38`). Epic `st-5qjq`; stage 1 is `st-eznu`. Design of
record: `docs/a2a/2026-08-30-coo-to-strader-live-execution-service-plan.md`.

**Stage 1 cannot reach a broker.** The only broker in the package is
`MockBroker`. There is no HTTP client, no credential on disk, and no import of
the repo's hobbled `schwab` library. See §8.

### 5.1 Running it

```
.venv/bin/python -m execd --mock --state-dir /var/lib/execd --mock-unlock
```

| Flag | Default | Effect |
|---|---|---|
| `--mock` | **required** | Run against `MockBroker`. Its absence exits **2** with a message; it is not a default. |
| `--state-dir DIR` | `/var/lib/execd` | The journal directory and the STOP file live here. |
| `--bounds FILE` | `/etc/execd/bounds.yaml`, then the start values | Bounds YAML. |
| `--port N` | `8778` | Loopback port. |
| `--host H` | `127.0.0.1` | Suppressed from `--help`. Any other value exits **2**: `execd: refusing to bind <h> — this API is loopback-only.` |
| `--mock-unlock` | off | Arms the service with `{"mock": True}` so the API can be exercised. Without it the service comes up **LOCKED** and refuses everything. |

Exit codes: `2` for a missing `--mock` or a non-loopback `--host`; otherwise the
process runs until killed.

On start it prints to stderr:
`execd <sha> on 127.0.0.1:<port> — broker=mock, state=<dir>, arming=<state>`.

`installed_sha()` shells `git -C <repo> rev-parse --short HEAD` with a 10s
timeout and returns `"unknown"` on any failure — so a copy installed at
`/opt/execd` that is not a checkout stamps `unknown` rather than lying about a
version. Every journal line carries this sha.

### 5.2 The API — fourteen routes

`execd/api.py`. Loopback only, JSON in and out. Flask, `threaded=True`.

| Method | Route | Query / body | Answers |
|---|---|---|---|
| GET | `/status` | — | the whole status object, §5.3 |
| GET | `/quote` | `?symbol=` (required) | `Quote.to_dict()` |
| GET | `/chain` | `?root=` (required), `?expiry=` | the broker's chain object verbatim |
| GET | `/orders` | — | `{"orders": [OrderResult…]}` |
| GET | `/positions` | — | `{"broker": [Position…], "tracked": [OpenPosition…]}` |
| GET | `/journal` | `?n=` (default 50, clamped to 1–1000) | `{"entries": [...]}` |
| POST | `/preview` | an intent object | `{"refused": null, "preview": {...}, "would_send": bool}` |
| POST | `/place` | an intent object | §5.6 |
| POST | `/cancel` | `{"order_id": "..."}` | `{"refused": null, "order": {...}}` |
| POST | `/flatten` | `{"reason": "..."}` optional | `{"refused": null, "closed": [...], "errors": [...]}` |
| POST | `/stand-down` | — | the status object |
| POST | `/stop` | — | the status object. **Ungated on purpose.** |
| POST | `/observe` | `{"spx": 6320.5}` | `{"spx": …, "fired": [...]}` |
| POST | `/poll-fills` | — | `{"picked_up": [...]}` or `{"picked_up": [], "error": "..."}` |

Status codes: `200` acted or answered a read · `400` not a valid intent
(malformed, not refused), body `{"error": "bad_request", "detail": "..."}` ·
`409` a bound refused it, body `{"refused": {"bound": "...", "reason": "..."}}` ·
`502` the broker could not be reached, body `{"error": "broker", "detail": "..."}` ·
`404` no such route.

**Deliberately absent: `/unlock`, `/resume`, and any re-auth route.**
`tests/execd/test_api.py::test_the_url_map_holds_exactly_the_narrow_door` pins
the app's rule set to exactly these fourteen, and a second test names
`/unlock`, `/arm`, `/resume`, `/reauth`, `/re-auth`, `/oauth` explicitly. Adding
**any** route breaks the suite, not only an arming one. An agent that can reach this API can ask
the service to trade inside Steve's bounds. It cannot arm it, cannot clear his
STOP, and never sees the credential.

`ExecService` does have `unlock()`, `resume()` and `lock()` methods — they are
reached from Steve's tailnet page, which is stage 3 and does not exist yet.

### 5.3 The status object

```
now, now_ct, sha,
arming:    {state, killed, kill_file, unlocked_at, expires_at, expires_at_ct,
            permits_entry, permits_exit}
day:       {open_positions, realized_loss_usd, attempts_used, attempts_left,
            loss_headroom_usd}
positions: [OpenPosition…]
bounds:    {the thirteen bound values}
journal:   the path to today's file
```

### 5.4 The intent — what a caller may hand the service

`execd/intent.py`. Frozen dataclass, JSON on the wire.

| Field | Type | Notes |
|---|---|---|
| `intent_id` | str | **the idempotency key**. Must match `^[A-Za-z0-9][A-Za-z0-9._:-]{2,79}$` — 3 to 80 characters. |
| `symbol` | str | 21-character OCC, root padded to six with spaces: `SPXW  260822C06300000` |
| `side` | `BUY_TO_OPEN` \| `SELL_TO_CLOSE` | |
| `qty` | int > 0 | booleans rejected |
| `order_type` | `LIMIT` \| `MARKET` \| `STOP` | default `LIMIT` |
| `limit` | float > 0 | required for `LIMIT`; a `MARKET` order carrying one is rejected |
| `stop_price` | float > 0 | required for `STOP` |
| `stop_spx` | float | entries: the SPX level at which the service exits |
| `delta` | float, `0 < |delta| <= 1` | entries: the option's delta at compose time |
| `source` | str | `intent-desk` \| `rule:<id>` \| `flatten` \| `protective-stop` |
| `engine_sha` | str | |

It never carries a credential, an account, or anything the service would trust
over its own bounds. `max_cost_usd` is derived as `limit * 100 * qty` for a
LIMIT and `None` otherwise.

`parse_occ` raises `not an OCC option symbol: <symbol>` or
`bad expiry in OCC symbol <symbol>: <detail>`.

### 5.5 The bounds — what it refuses, whatever the caller asks

`execd/bounds.py`. Pure functions over frozen data: an intent, the day's state,
a quote, a clock reading. No I/O, no broker, no credential.

There are **twelve distinct bound names** — `armed`, `instrument`, `side`,
`order_type`, `qty`, `stop`, `protective_stop`, `window`, `positions`,
`ceiling`, `price_band`, `preview_cost`. The table below has fourteen rows
because `ceiling` and `protective_stop` each refuse on two separate conditions.

**Order of checks for an entry** (`check_entry`), and the order is asserted in
`tests/execd/test_bounds.py`. Cheapest and most categorical first, so a refusal
names the most fundamental thing wrong:

| # | `bound` | Condition that refuses |
|---|---|---|
| 0 | `armed` | arming state is LOCKED or STOOD_DOWN (checked before the bounds, in `_entry_refusal`) |
| 1 | `instrument` | OCC root not in `instruments` (`SPX`, `SPXW`) |
| 2 | `side` | side is not `BUY_TO_OPEN` |
| 3 | `order_type` | order type is not `LIMIT` |
| 4 | `qty` | `qty > qty_cap` |
| 5 | `stop` | the STOP file exists |
| 6 | `protective_stop` | `require_protective_stop` and either `stop_spx` or `delta` is missing |
| 7 | `window` | weekend; or before `open_ct`; or at/after `no_open_after_ct` |
| 8 | `positions` | `open_positions >= max_open_positions` |
| 9 | `ceiling` | `attempts_used >= max_attempts` |
| 10 | `ceiling` | `realized_loss_usd >= daily_loss_ceiling_usd` |
| 11 | `price_band` | no quote; or quote older than `max_quote_age_s`; or not two-sided; or limit above `ask*(1+band)`; or limit below `bid*(1-band)` |
| 12 | `protective_stop` | no `$SPX` mark; or the stop sign is transposed (`stop_is_consistent` false) |
| 13 | `preview_cost` | the broker's preview total exceeds `max_cost_usd + preview_cost_tolerance_usd`; or the broker would not accept the order |

Steps 12 and 13 run inside `ExecService`, not `check_entry` — 12 in
`_protective_stop_refusal`, 13 in `_place_entry` after the broker preview.

**An exit clears three things only** (`check_exit`): the instrument, that the
side really is `SELL_TO_CLOSE`, and — *only when the service knows the size* —
that `qty <= held_qty`. When `held_qty` is `None` the order goes through, because
refusing on ignorance is how an exit gate traps someone. Not the window, not the
ceiling, not the STOP file, not stand-down. The one thing that refuses an exit
is LOCKED, and that is a statement about capability, not policy.

### 5.6 `POST /place` — the one path that transmits

1. Validate the intent. Malformed → `400`.
2. **Idempotency.** `_replay(intent_id)` scans today's journal for a `placed`
   line with that id. A hit journals `replayed` and returns the original order
   with `"replayed": true`. Nothing is re-sent.
3. Journal `request`.
4. Entry: run §5.5 steps 0–12 → on refusal journal `refused` and return `409`.
5. Broker `preview()`. A `BrokerError` journals `error` and raises → `502`.
   Journal `preview`.
6. If the preview is not accepted → `409` with bound `preview_cost` and the
   broker's own messages. Then `check_preview_cost` → `409` on breach.
7. Read the `$SPX` mark. `broker.place(intent)`. Journal `placed` with the sha,
   the spx and the order.
8. `REJECTED` → journal `rejected`, return with `stop_order: null`.
   Not filled → return with `stop_order: null`.
9. Filled → build `OpenPosition`, journal `filled` (carrying `stop_spx` and
   `delta` on the fill line, so a restart recovers a position the SPX-mark loop
   can watch even if the resting stop failed), then place the protective stop.

### 5.7 The protective stop

`execd/stops.py`. `PREMIUM_TICK_PTS = 0.05`, `CONTRACT_MULTIPLIER = 100`.

Two stops, not redundant:

1. **The resting stop on the option**, placed the moment a fill comes back. It
   is what is still standing if this box OOMs at three in the morning — which
   has happened.
2. **The SPX-mark exit loop** (`ExecService.observe`), accurate while the box is
   alive. It sends a market close the moment the level trades and cancels the
   resting order.

Arithmetic: `premium_at_stop = fill_px - |spx_now - stop_spx| * |delta|`,
rounded **up** to the 0.05 tick — toward the fill, the tighter of the two valid
ticks, because rounding down would let the realized loss sit up to one tick
($5 a contract) beyond the budget the distance was derived from. Then two
clamps: at least one tick, and at most `fill_px - tick`. A first-order estimate
and honestly so — gamma means a long option decays toward the stop more slowly
than delta predicts, so it errs toward triggering slightly early.

`protective_stop_price` raises rather than guessing when `fill_px <= 0`,
`delta` is outside `(0, 1]`, the stop distance is zero, or the fill leaves no
room above the tick.

`exit_triggered(right, spx, stop_spx)`: a long **call** triggers on
`spx <= stop_spx`; a long **put** on `spx >= stop_spx`. `stop_is_consistent` is
the negation at compose time — a call stop above the market or a put stop below
it is already triggered, which is a transposed sign, not a trade.

**Partial exits.** A stop sized for the whole position would sell contracts
Steve no longer owns, so a partial fill cancels the resting stop and rests a new
one at the same price for what is left (`_settle`, and again in `poll_fills`).
`_rest_stop_at` is the **only** place a resting stop is created, so its size can
never drift from the position.

A failure to rest the stop journals `stop_unprotected` — loud, because the
position is live and unprotected until the SPX-mark loop or Steve deals with it.

### 5.8 The journal

`execd/journal.py`. One `YYYY-MM-DD.jsonl` file per **Central** trading day
under `<state-dir>/journal/`. Every line is written, flushed and `fsync`'d
before the call returns.

Every line carries `ts`, `ts_ct`, `event`, `sha`.

Events: `request` · `refused` · `preview` · `placed` · `rejected` · `filled` ·
`stop_placed` · `stop_unprotected` · `exit_triggered` · `exit_unfilled` ·
`closed` · `canceled` · `flattened` · `replayed` · `error` · `unlock` ·
`stand_down` · `lock` · `stop` · `resume` · `recovered` · `unreadable`.

`unreadable` is not written — it is *synthesised on read* when a line will not
parse, which is what a kill mid-write looks like. Surfacing it as data rather
than raising means the rest of the day is still the audit.

**The day is derived, not remembered.** `day_state()` rebuilds
`open_positions`, `realized_loss_usd` and `attempts_used` by reading the file,
so a restart mid-session recovers the ceiling rather than resetting it.
`attempts_used` counts `filled`+`kind=entry` lines. A partial close debits the
loss immediately but only frees the position slot when `remaining_qty` is
falsy. **Losses only debit** — a winning trade does not buy back an attempt or
raise the ceiling. That is FD0's `Budget` semantics carried across unchanged.

Read API: `read(day)`, `days()`, `find(intent_id, day)`, `tail(n, day)`,
`events(*names, day)`, `day_state(day)`, `path_for(day)`, `today()`.

### 5.9 Arming

`execd/arming.py`. Three states crossed with a STOP file.

| State | Meaning | Entries | Exits |
|---|---|---|---|
| `LOCKED` | no credential in memory — the state after **every** restart | no | **no** (nothing to transmit with) |
| `ARMED` | Steve entered the passphrase | yes | yes |
| `STOOD_DOWN` | finished for the day, credential still in memory | no | yes |

Arming expires at the session close (`session_close`, today's `close_ct` in CT).
**Expiry stands down rather than locking**, so the credential stays available to
close whatever is still open at the bell.

The **STOP file** is `<state-dir>/STOP`. One `touch` from anywhere, including
Steve's phone. It blocks entries in every state and blocks no exit in any.
`stop()` is idempotent and cannot fail on an existing file. `resume()` is
page-only — an agent must not be able to undo the kill switch.

The rule the module exists to hold: *nothing here may ever refuse an exit for a
risk reason.*

### 5.10 The bounds file

`/etc/execd/bounds.yaml`, seeded once from `execd/bounds.example.yaml` by
stage 3's `deploy/install.sh`. After that it is Steve's to edit; the service is
restarted to pick up a change.

| Key | Start value |
|---|---|
| `instruments` | `[SPX, SPXW]` |
| `qty_cap` | `1` |
| `max_open_positions` | `1` |
| `daily_loss_ceiling_usd` | `100.0` |
| `max_attempts` | `2` |
| `open_ct` | `"08:30"` |
| `close_ct` | `"15:00"` |
| `no_open_after_ct` | `"14:50"` |
| `weekdays_only` | `true` |
| `price_band_pct` | `0.10` |
| `max_quote_age_s` | `30.0` |
| `preview_cost_tolerance_usd` | `5.00` |
| `require_protective_stop` | `true` |

**An unknown key is a start-up error, not a silent default** — a typo must not
leave the service running under limits Steve did not choose. Validation also
rejects an empty `instruments`, `qty_cap < 1`, `max_open_positions < 1`, a
non-positive ceiling, `max_attempts < 1`, `price_band_pct` outside `(0,1)`, a
non-positive `max_quote_age_s`, `open_ct >= close_ct`, and a
`no_open_after_ct` outside the window. A file that exists but is wrong **raises**;
a file that is absent falls back to the start values.

The *shape* of the bounds is not configurable. There is no key that switches a
bound off, because a bound you can switch off is not a bound.
`require_protective_stop` exists as a key only so the refusal has something to
name.

### 5.11 The broker seam

`execd/broker.py`. The `Broker` protocol is **eight methods**: `quote`, `chain`,
`preview`, `place`, `cancel`, `orders`, `positions`, `fills_since`. (The
docstring says seven — see §12.) All data in, data out, no credential.

`BrokerError` is the **absence** of an answer, distinct from a rejection, which
is a fact the broker asserted. The service journals both and retries neither —
an execution service that retries by itself is a service that double-sends.

`MockBroker` is deliberately opinionated: it fills a buy at `min(limit, ask)`
and a market sell at the bid, rests STOP orders as `WORKING`, and records every
call in `.calls`. Test knobs, each consumed by one call unless noted:
`reject_next` (message for the next `place`), `fail_next` (`BrokerError` from
the next call), `rest_limits` (standing: limits rest instead of filling),
`partial_fill_qty` (next fill takes only this many). Test-only helpers:
`trigger_stop(order_id)`, `working_orders(symbol)`, `calls_to(method)`,
`set_quote`, `set_chain`, `set_position`.

`COMMISSION_PER_CONTRACT_USD = 0.65` — Schwab's published options rate; stage 2
reads the real one.

### 5.12 Recovery

`_recover()` runs in the constructor. It replays today's journal and rebuilds
`_open` from `filled`+`kind=entry`, `stop_placed` and `closed` lines, then
journals `recovered` if anything survived. The service comes back **LOCKED**, so
it cannot open anything; what it must not do is come back not knowing a position
is live, because then the SPX-mark loop stops watching it and `flatten` misses
it.

### 5.13 The vault (stage 2's first piece, already landed)

`execd/vault.py`. A single file holding a JSON payload encrypted with
**AES-256-GCM** under a key derived by **scrypt** (`n=2^15, r=8, p=1,
dklen=32`, 16-byte salt, 12-byte nonce) from a passphrase Steve types into the
service's page and never writes down.

- **No passphrase on disk. No key file. No recovery** — a forgotten passphrase
  means re-authorising with Schwab.
- The work factors are written **into the file** and authenticated with the
  ciphertext as AAD, so nobody can quietly rewrite `n` down to 1 and leave a
  file that still decrypts but is cheap to attack.
- Payload-agnostic on purpose: it knows nothing about Schwab, OAuth or token
  shapes, which is what lets the whole thing be tested with no credential in the
  room.
- It does not log — not the passphrase, not the payload, not a truncated preview
  of either — and does not return the payload from `info()`.
- Writes are atomic: temp file, `fsync`, `os.replace`, `chmod 0600`, then
  `fsync` on the directory.
- `MIN_PASSPHRASE_LEN = 12`, enforced **on write** so the complaint arrives while
  Steve is choosing, never while he is trying to open a vault he already made.
  A leading or trailing space is refused, because a space a form silently trims
  is a vault that stops opening.
- API: `store(payload, passphrase)`, `load(passphrase)`, `verify(passphrase)`,
  `rotate(old, new)`, `info()`, `exists`. Errors: `VaultMissing`,
  `VaultCorrupt`, `BadPassphrase` — and `BadPassphrase` is indistinguishable
  from a tampered file on purpose, because AES-GCM authenticates the ciphertext
  and there is nothing safe to guess.
- **One honest limit**: Python strings cannot be reliably wiped from memory. The
  derived key is held in a `bytearray` and zeroed after use; the passphrase you
  pass in may survive in the interpreter's heap. The credential is protected
  *at rest*. Protecting it in memory from a root process on the same box is the
  process boundary the design names as a residual.

### 5.14 The stage ladder

| Stage | Bead | What lands |
|---|---|---|
| 1 | `st-eznu` | **done** — everything in §5 against `MockBroker` |
| 2 | `st-w2nw` | the Schwab transport: Trader API over HTTPS, in-service re-auth. A second `Broker`; nothing else changes. The vault is done; the client is blocked on recorded response shapes. |
| 3 | `st-p8k8` | dedicated user, systemd unit, `deploy/install.sh`, the tailnet page that takes the passphrase, the plaintext token retired |
| 4 | `st-k6gl` | one 1-lot live single with Steve at the STOP button |
| 5 | `st-47i2` | FD0 tickets and promoted rules become intents; the paste line retires |

**Order is strict. Nothing sends before stage 4.**

---

## 6. The feed and the credential

### 6.1 Preflight

```
.venv/bin/python -m strader.execution.feed --preflight --token tokens/schwab_token.json
```

Flags: `--probe`, `--preflight`, `--fixture PATH`, `--token PATH`,
`--samples N` (default 3). **`--token` defaults to `~/schwab_token.json`, which
is the wrong path** — pass it explicitly. Prints PASS/FAIL for the token, the
SPX quote stream (three moving ticks), the chain, the budget ledger and the
journal. Two lines are Steve's and default to FAIL until he says otherwise: the
thinkorswim conditional-exit reload, and "build plan complete".

### 6.2 The seven-day wall

Schwab refresh tokens die **seven days after they are minted**, used or not.
When the wall is hit the feed goes dark on the next call — it happened silently
on 2026-07-08, which is why the checks exist.

- The 06:30 corpus job checks it Monday to Saturday and writes
  `data/corpus/_schwab_token_health.json`. It warns at 2 days left, alarms at 1.
- **An expiry during the day is not seen until the next morning.** That is a
  stated blind spot in `docs/live-monitoring-registry.md`.
- Manual check: `.venv/bin/python scripts/schwab_token_health.py --no-bead --no-push`
  — exit 0 healthy, 1 action needed.

### 6.3 Re-auth

```
.venv/bin/python scripts/refresh_schwab_token.py
```

No arguments, no `--help` — anything typed after the script name starts the
flow. It prints a login link; the redirect page **will not load, and that is
expected**; the whole address from the address bar is pasted back at the
prompt. The script then checks the grant's shape *and* makes one cheap
market-data call — both must pass before it reports done. It keeps the last ten
backups beside the token. An agent can run everything up to the login link; the
login itself is Steve's, because it needs a browser session.

---

## 7. The fire server

`scripts/fire_server.py`. The phone-reachable ARM → FIRE page. Binds the
tailnet address on port **8777**, refuses to start if the tailnet is down,
reached as `https://mydesk-1.tail89f676.ts.net` — never the LAN, never the
public internet.

It is a **dry run**: FIRE journals the ticket and transmits nothing, printing
`DRY RUN COMPLETE — nothing transmitted`. The registry lists it as *never
launched — leave alone; promotion needs explicit review*.

Rails, measured in the source:

- `QTY_CAP = 1` — a ticket asking for more than one contract cannot ARM.
- `STALE_MIN = 10` — a ticket staged more than ten minutes ago cannot ARM.
- `NONCE_TTL_S = 60` — ARM mints a single-use code good for sixty seconds.
- Kill file `data/exec/FIRE_DISABLED` — one `touch` disables ARM and FIRE;
  removing it re-enables them.
- **`/exit-all` is deliberately not blocked by the kill switch.** The kill file
  stops the machine *entering* trades; blocking exits would trap Steve at the
  moment he most needs out.

Routes: `GET /health`, `GET /`, `GET|POST /arm`, `GET|POST /fire`,
`GET|POST /exit-all`, `POST /exit-all/confirm`. `--port N` is the only flag.

Steve's ruling of 2026-08-30 — the control surface is served from this box over
the tailnet, not from Azure — means execd's stage-3 page is built on this
server's footing. Nothing about that ruling changes the wall.

---

## 8. The wall

Four independent layers stop an order going out, and execd is a deliberate,
narrow, tested exception to the fourth.

1. **The broker library has no order functions.** The repo's copy of schwab-py
   is a fork with `place_order`, `replace_order`, `cancel_order`,
   `preview_order` and every account and transaction call removed —
   "unrecoverable from within this codebase"
   (`lib/schwab-py/schwab/client/base.py:131-141`).
2. **The gate key.** Any live Schwab client refuses to build unless
   `~/.schwab_gate_key` exists (`broker_schwab/client.py:31-36`) — a file only
   Steve creates.
3. **The hook.** Any agent script importing the Schwab code is blocked before it
   runs, except the two quote and chain readers
   (`.claude/hooks/scripts/schwab-gate.sh:74-92`).
4. **The fire server transmits nothing** (`scripts/fire_server.py:303-324`). The
   live client that would change that is a separate build (`st-bxls`) behind
   `~/.schwab_fire_key`, which does not exist.

**execd's exception.** `tests/execd/test_wall.py` (38 tests) asserts, by reading
the AST of every module under `execd/` *and* by watching what a full import
actually loads:

- `FORBIDDEN_ROOTS = {schwab, broker_schwab, schwab_py}` — execd will speak
  plain HTTPS in stage 2 and never import the hobbled library, so the hook keeps
  its meaning unchanged.
- `FORBIDDEN_TRANSPORTS = {httpx, requests, urllib3, socket, http.client, aiohttp}`
  — **there is no transport at all today.** Stage 2's Trader API client
  (`execd/schwab.py`) adds exactly one (`httpx`) in a new module and **drops it
  from this set in the same commit**, deliberately and visibly, not as a side
  effect of an import someone added.
- No module under `execd/` names a **plaintext** credential file. The vault owns
  the encrypted store; what must never appear is a path anyone can read.

Crossing the wall was Steve's ruling of 2026-08-30 (`st-l3s4`), taken as its own
event and never as a side effect of a commit.

---

## 9. Files and directories

| Path | Written by | Contents |
|---|---|---|
| `data/intent/<day>.json` | intent desk, every verb | the DayPlan |
| `data/intent/staged/<stamp>-<shape>.json` | intent desk, `go` | the staged ticket, paste line, OCC legs, FD0 block |
| `data/exec/FIRE_DISABLED` | Steve, `touch` | fire-server kill switch |
| `data/corpus/_schwab_token_health.json` | the 06:30 corpus job | token staleness |
| `tokens/schwab_token.json` | `refresh_schwab_token.py` | the plaintext token, retired at execd stage 3 |
| `tests/fixtures/tos/<shape>.txt` | Steve, pasted | TOS confirm text; **directory does not exist** |
| `<state-dir>/journal/<day>.jsonl` | execd | the append-only audit |
| `<state-dir>/STOP` | anyone, `touch` | execd kill switch |
| `/etc/execd/bounds.yaml` | `deploy/install.sh` once, then Steve | execd bounds |
| `~/.schwab_gate_key` | Steve, 2026-05-21 | gate-key layer; exists, empty |
| `~/.schwab_fire_key` | — | fire-key layer; **does not exist** |

FD0's own paths come from `journal_path_for(day, root)` and
`state_path_for(day, root)`.

## 10. Tests

All five counts measured 2026-08-30 between 14:05 and 14:20 CT, on `main`.

| Suite | Count | Command |
|---|---|---|
| execd, all | **365** | `.venv/bin/python -m pytest tests/execd` |
| `strader/tests` tree | **332** | `.venv/bin/python -m pytest strader/tests` |
| intent + fd0 within it | **191** | `.venv/bin/python -m pytest strader/tests -k "intent or fd0"` |
| fire server | **16** | `.venv/bin/python -m pytest tests/scripts/test_fire_server.py` |
| token tools | **27** | `.venv/bin/python -m pytest tests/scripts/test_refresh_schwab_token.py strader/tests/test_schwab_token_health.py` |

`pyproject.toml` sets `testpaths = ["tests", "strader/tests"]` — **both** trees.
Bare `pytest` collecting only the small one is a fixed bug (`st-hw5e`); any
session reporting "186 passed" as its quality gate ran none of the orderflow
layer.

## 11. What does not exist

Named plainly, because a manual that lets a reader assume otherwise is worse
than no manual.

- **No console script.** No `strader` command; no `[project.scripts]`.
- **No client for execd.** Fourteen routes and no command-line caller. Today
  the operator surface is `curl`.
- **No join between the intent desk and execd.** `go` writes a paste line;
  execd takes an `OrderIntent`. Stage 5.
- **No live chain snapshot for `price`.** It reads a hand-made JSON file.
- **No `vertical` or `condor` pricing**, though both are in the `Vehicle` type.
- **No TOS fixtures**, so every paste shape reports `inferred`.
- **No transport in execd.** Mock broker only.
- **No systemd unit, no `deploy/install.sh`, no tailnet page** for execd —
  stage 3.
- **`data/intent/` does not exist.** The desk has never been run for real.
- **The market-versus-limit decision, the bounded chase, and the hard-ceiling
  loop** described in Desk's intent v2 are not built. They are planned as paper
  first (`st-p7zw`, `st-kdaq`, `st-uaxf`).

## 12. Counts in the tree that were wrong

Found while writing this manual, on 2026-08-30. The two in code were corrected
in the same commit as this document; the third is left alone deliberately.

| Where | Said | Actually | Action |
|---|---|---|---|
| `execd/api.py:3` | "Ten routes, no policy" | fourteen | **fixed** |
| `execd/broker.py:4,159` | "seven methods" | eight | **fixed** |
| `myDesk/reports/2026-08-30-execution-service-stage-one.md` (COO) | "318 tests for the new service" | 365 | **left as written** — it is a point-in-time report Steve has already read, and it was true at 12:15 CT before the vault's 44 tests landed. Rewriting a report after the fact is worse than a stale number in a dated document. |

`execd/README.md` says "Fourteen routes" and was already correct.

The general lesson for anyone reading this tree: **a count in a docstring is
not a measurement.** Where a number matters, run the command in §10.
