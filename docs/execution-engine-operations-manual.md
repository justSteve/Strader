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
| **Intent desk** — speak the day, get a paste line | `strader/intent/` | works; since 2026-09-14 `go` also hands a priced single to execd for a **preview** (§3.11) | No. The desk's client has no place; the paste line stands. |
| **FD0** — budget-derived stop, exit block, attempt ledger | `strader/execution/` | works, as a library | No. Renders text. |
| **execd** — the live execution service | `execd/` | stages 1–3 of 5 built and installed (2026-09-14): mock broker, the Schwab transport, the systemd unit and the tailnet page; stage 4's preview rehearsal wired | **Yes, by design, and only it** — through `/place`, which nothing in the tree calls yet. Nothing sends before stage 4's one live ticket with Steve at the STOP button. |
| **Fire server** — ARM → FIRE page on the tailnet | `scripts/fire_server.py` | built, never launched, dry run | No. Journals `transmitted: false`. |
| **Schwab read feed + token** | `strader/execution/feed.py`, `broker_schwab/`, `scripts/refresh_schwab_token.py` | works, read-only | No. Order calls are removed from the library. |

The two halves meet on **preview** only (stage 4's rehearsal, `st-k6gl`,
2026-09-14): the intent desk still produces the **paste string** for Steve's
hands, and `go` also hands the same ticket to execd as an **OrderIntent JSON**
over the loopback API for a preview — every bound applied, the broker's own cost
line, nothing sent. Routing `place` through the desk is stage 5 (`st-47i2`).

## 2. Every entry point, complete

There is **no console script**. `pyproject.toml` has no `[project.scripts]`
table (checked 2026-08-30), so nothing installs a `strader` command; everything
is `python -m` or a path to a script. There are exactly two `__main__.py` files
in the repo outside `.venv` and `lib`.

| Command | Kind | What it is |
|---|---|---|
| `python -m strader.intent` | interactive REPL | The intent desk. §3. |
| `python -m execd --mock …` | long-running server | execd. Its operator surface is HTTP, not argv. §5. |
| `bash deploy/install.sh --execd` | one command, Steve's | Stage 3 (st-p8k8): creates the `execd` user, copies `execd/` to `/opt/execd`, builds its venv, seeds `/etc/execd/bounds.yaml`, writes the market credential, asks for the vault passphrase, installs and starts `strader-execd.service`, publishes the page. Idempotent; `--dry-run` prints the plan. §5.15. |
| `https://mydesk-1.tail89f676.ts.net/exec/` | the page | Steve's surface on the tailnet: unlock, STOP, clear STOP, flatten, stand down, lock, weekly re-auth of both apps. Loopback `127.0.0.1:8779` behind `tailscale serve`. §5.15. |
| `python -m strader.execution.feed --preflight --token PATH` | one-shot check | Go/no-go preflight. §6. |
| `python scripts/fire_server.py [--port N]` | long-running server | Fire server. §7. |
| `reauthData` / `reauthAccount` | interactive chore | The shell handles for the weekly re-auth — app 1 (market data) and app 2 (trading). Each prints both walls before and after and names the other. `reauth` alone no longer runs anything; it says which two exist. §5.12a. |
| `python scripts/refresh_schwab_token.py [--trading]` | interactive chore | What those handles call. Without the flag it mints app 1 (market data); with it, app 2 (trading). Do both in one sitting. §5.12a, §6. |
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
| `--chain FILE.json` | — | Loads a chain snapshot. **Without `--chain`, `price` cannot run** and answers `No chain loaded — start with --chain FILE.json, or --chain live to fetch it through execd.` A missing file exits 2. |
| `--chain live` | — | `price` fetches the SPX chain through execd's market door (`GET /marketdata/chains`) **at each `price`**, for the day's expiry. Answers while the service is LOCKED. When the service is down: `Could not fetch the live chain: execd unreachable at …`. §3.11. |
| `--expiry YYYY-MM-DD` | the day | Which expiry the live chain is for. |
| `--execd URL` | `http://127.0.0.1:8778` (`EXECD_URL`) | Where `go` sends its preview. §3.11. |
| `--no-execd` | off | `go` ends at the paste line; nothing goes to the service. |
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

`--chain live` builds the same `Chain` from Schwab's own chain body through
execd (`market.ingest.schwab.chain_from_schwab`), so the hand-made file is for
tests and replays; the desk prices on the live chain since 2026-09-14 (§3.11).

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
| `go` | — | the staged paste line and legs, then execd's answer (§3.11) | writes `data/intent/staged/<stamp>-<shape>.json`; a single goes to execd as an intent for a **preview**, journaled under `desk-<stamp>`; **sends nothing** |
| `send` | — | `SENT AND FILLED: order …`, `SENT: order … WORKING …`, or the refusal | **the one verb that transmits**: the intent `go` previewed, same id, to `POST /place`; refused at the desk unless the last `go` was accepted by execd within ten minutes; a repeat is answered from the service's journal, never re-sent (§3.11) |
| `stand down` / `cancel` | — | `Standing down. Nothing priced, nothing pending.` (+ `Withdrew the staged ticket desk-…; send will refuse it.`) | clears orders, bracket and pending; marks the newest staged record `withdrawn_at`, so `send` refuses it |
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

The `execd` block (present whenever a service is wired) holds `routed`, and
then either `reason` (a fly: `the service sends single legs only`), or the
`intent` as sent plus `status` and `answer` (the service's body: `preview` on
200, `refused.{bound, reason}` on 409), or `intent` plus `error` when the
service did not answer. The record is written before the service is asked and
rewritten with the answer, so a fault on the wire cannot lose the ticket.

`data/intent/` is gitignored. The first real run against the installed
service was 2026-09-14 07:39 CT from a scratch plan directory (§3.11).

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

### 3.11 The join to execd — preview only (stage 4 rehearsal, `st-k6gl`)

`strader/intent/execd.py`. Plain HTTP to the loopback with the standard
library; imports neither `schwab` nor `broker_schwab`, so the gate hook is
untouched. Two calls, and no third:

| Call | Route | What comes back |
|---|---|---|
| `DeskExecd.chain(expiry)` | `GET /marketdata/chains?symbol=$SPX&contractType=ALL&strikeCount=40&includeUnderlyingQuote=true&fromDate=…&toDate=…` | Schwab's chain body; `live_chain()` turns it into the `Chain` that `price` resolves against. Answers while LOCKED. |
| `DeskExecd.preview(intent)` | `POST /preview` | 200 with `preview.{price, cost_usd, commission_usd, total_usd, accepted, messages}`; 409 with `refused.{bound, reason}`; 400 malformed; 502 broker down. |

**`send` is the third call** (`DeskExecd.place`, `POST /place`), added the
same morning on Steve's word ("i want to see the full life cycle now"). It
sends exactly the intent the last `go` staged and execd previewed, under the
same id; the desk refuses when nothing is staged, when that preview was not a
200, or when the record is older than ten minutes. The service runs its rules
and the broker's preview again before the order goes, rests the protective
stop on the fill, and the watcher (§5.16) feeds it the SPX mark from then on.
There is no cancel, flatten or stop on the desk — those are the page.

**The life cycle, in the words the desk answers with:** `single …` → `price`
(the live chain, the paste line, FD0's stop) → `go` (`Execd preview, nothing
sent: … cost $…; the broker accepts it.`) → `send` (`SENT AND FILLED: order
N, 1 at 2.10 ($210.00). Protective stop resting at the broker: order M at
1.45. The service watches the SPX mark; STOP and FLATTEN are on your page.`)
→ the exit: the watcher fires FD0's SPX-level exit, or the broker's stop
fills, or FLATTEN on the page → the journal, read back against Schwab's
orders. `tests/execd/test_desk_join.py` walks that whole path over the mock.

**The intent** (`intent_for`): one OCC leg from `occ_symbols`, `BUY_TO_OPEN`,
the lot count, `LIMIT` at the priced ask, `source: intent-desk`, `engine_sha`
(the desk's commit, `-dirty` when the tree is), and — when FD0 built a
bracket — `stop_spx` (the ticket's `stop_trigger_spx`) and `delta` (the leg's
delta at compose), the two numbers the service derives the broker-resident
stop from. A single with no bracket still goes; the service's own
`protective_stop` bound refuses it, and that refusal is the record. A fly is
not routed (the service sends single legs only) and the record says so.

**The id** is `desk-<stamp>`, the staged file's stamp, so the desk's record,
the service's journal lines (`request` kind `preview`, then `preview` or
`refused`) and, later, the one live ticket carry the same name.

**The read-back** after the paste line, one of:

- `Execd preview, nothing sent: SPXW  260914C07655000 BUY_TO_OPEN x1 LIMIT at 21.20 — cost $2120.00, commission $0.65, total $2120.65; the broker accepts it.` (a rejected preview says `the broker would REJECT it.` and lists the broker's messages)
- `Execd refused (window): 07:39 CT is before the session opens at 08:30. Nothing sent.`
- `Execd not reachable (execd unreachable at http://127.0.0.1:8778: …). Staged only, nothing sent.`
- `Not previewed through execd: the service sends single legs only; this order has 4. The paste line stands.`

**Measured 2026-09-14 07:39 CT** against the installed service (sha aa83668,
ARMED by Steve at 07:26): `--chain live` returned the day's SPX chain through
the door; `price` resolved a 1-lot 0DTE call at the ask with an FD0 bracket;
`go` staged the record and the service journaled `request` then `refused`
(`window`) under `desk-20260914T073956`. The broker was not asked — the bounds
come first. The first preview that reaches Schwab needs the session window
(08:30–14:50 CT) and the service ARMED.

**Paper first.** With `/etc/execd/mode` at `paper` (§5.17) the same
`send` fills in the simulated book against live quotes and every read-back
is prefixed `PAPER (simulated) — `; the broker's preview is still Schwab's.

**Every change to `execd/` reaches the running service only through the
install** (the copy at `/opt/execd` is Steve's to write). The handle is
`installExecd` (COO `factory/templates/bashrc.d/execd-install.sh`): pulls
Strader fast-forward only, runs the install, reminds that the restarted
service is LOCKED until unlocked on the page. Interactive terminals only.

**The raw preview shape.** The bead's residue from `st-p9mx`: the preview,
place and cancel bodies in `tests/execd/test_schwab.py` are spec-derived. The
transport now keeps Schwab's raw preview body on the `Preview` (`raw`, outside
`to_dict`) and the service journals it as a `preview_raw` line under the
intent id. The installed copy picks this up at the next `bash deploy/install.sh
--execd`; the first in-window preview after that records the real shape, which
then replaces the SPEC fixture in the same commit.

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

Source: `execd/`, **9,092 lines across 19 modules** (`cat execd/*.py | wc -l`,
2026-09-15 06:00 CT, at `ab4cea7`; 2,631 across 11 on 2026-08-30). Tests:
`tests/execd/`, **883 passing in 26 s** (2026-09-15 09:10 CT, after §5.22;
365 on 08-30, 856 before §5.22). Run `.venv/bin/python -m pytest tests/execd`
for today's number — this header was left saying 365 for two weeks and the
audit's finding about that is fair (§12). Epic `st-5qjq`; stage 1 is
`st-eznu`. Design of record:
`docs/a2a/2026-08-30-coo-to-strader-live-execution-service-plan.md`.

**Two brokers.** `MockBroker` (stage 1) and `SchwabBroker` (stage 2,
`execd/schwab.py`, the one module in the package with a transport — `httpx`).
No credential on disk here (the vault holds it), no import of the repo's hobbled
`schwab` library. See §5.11 and §8. Stage 2 landed 2026-09-04 with **540 tests
passing** in `tests/execd/` (schwab 89, wall 42).

### 5.1 Running it

```
.venv/bin/python -m execd --mock --state-dir /var/lib/execd --mock-unlock
```

| Flag | Default | Effect |
|---|---|---|
| `--mock` / `--schwab` | **one required** | Run against `MockBroker`, or against the Schwab Trader API (starts LOCKED). Neither is a default; both or neither exits **2**. |
| `--vault FILE` | `/etc/execd/vault.json` | The encrypted **trading** credential, for `--schwab`. Missing file exits **2**. |
| `--market-credential FILE` | none | The market-data app's credential (0600, service-owned), held outside the arming lock so quotes answer while LOCKED. Written by `scripts/execd_market_credential.py`. Absent: a warning, and reads fall back to the trading credential, so they stop working when the service locks. Unreadable or malformed exits **2**. |
| `--unlock-stdin` | off | With `--schwab`: read the passphrase from standard input (no echo on a terminal), open the vault, arm. The console path until the page exists (stage 3). Wrong passphrase exits **3**. |
| `--state-dir DIR` | `/var/lib/execd` | The journal directory and the STOP file live here. |
| `--bounds FILE` | `/etc/execd/bounds.yaml`, then the start values | Bounds YAML. |
| `--port N` | `8778` | Loopback port. |
| `--host H` | `127.0.0.1` | Suppressed from `--help`. Any other value exits **2**: `execd: refusing to bind <h> — this API is loopback-only.` |
| `--mock-unlock` | off | Arms the service with `{"mock": True}` so the API can be exercised. Without it the service comes up **LOCKED** and refuses everything. |

Exit codes: `2` for no broker flag, both flags, a missing vault, `--mock-unlock`
against `--schwab`, or a non-loopback `--host`; `3` when the vault does not open
or the unlock is refused; otherwise the process runs until killed.

On start it prints to stderr:
`execd <sha> on 127.0.0.1:<port> — broker=mock, state=<dir>, arming=<state>`.

`installed_sha()` shells `git -C <repo> rev-parse --short HEAD` with a 10s
timeout and returns `"unknown"` on any failure — so a copy installed at
`/opt/execd` that is not a checkout stamps `unknown` rather than lying about a
version. Every journal line carries this sha.

### 5.2 The API — sixteen routes

`execd/api.py`. Loopback only, JSON in and out. Flask, `threaded=True`.

| Method | Route | Query / body | Answers |
|---|---|---|---|
| GET | `/status` | — | the whole status object, §5.3 |
| GET | `/quote` | `?symbol=` (required) | `Quote.to_dict()` |
| GET | `/chain` | `?root=` (required), `?expiry=` | the broker's chain object verbatim |
| GET | `/orders` | — | `{"orders": [OrderResult…]}` |
| GET | `/positions` | — | `{"broker": [Position…], "tracked": [OpenPosition…]}` |
| GET | `/journal` | `?n=` (default 50, clamped to 1–1000) | `{"entries": [...]}` |
| GET | `/marketdata/<kind>` | `kind` ∈ `quotes`, `chains`, `pricehistory`; the query is Schwab's own parameter names for that resource, allow-listed | the raw Schwab body. Stage 3 (st-p8k8): what `broker_schwab.client.create_client()` returns speaks to this, so every reader in the repo reads through the one credential holder. Answers while LOCKED. |
| POST | `/preview` | an intent object | `{"refused": null, "preview": {...}, "would_send": bool}` |
| POST | `/place` | an intent object | §5.6 |
| POST | `/cancel` | `{"order_id": "..."}` | `{"refused": null, "order": {...}}` |
| POST | `/flatten` | `{"reason": "..."}` optional; **JSON required** | `{"refused": null, "closed": [...], "errors": [...]}` |
| POST | `/adjust` | `{"symbol": "...", "stop_price": 1.80, "target_price": 25.0}` — at least one price | `{"refused": null, "stop": {moved, old_price, new_price, order_id, stop_spx}, "target": {...}, "closed": null}`; `409` names the refusal (`bracket`, `tick`, `ceiling`, `position`, `exit_in_flight`, `filled`, `armed`); `502` the broker. §5.20 (st-fn5y) |
| POST | `/stand-down` | `{}`; **JSON required** | the status object |
| POST | `/stop` | — | the status object. **Ungated on purpose, and takes no lock** — the kill file is touched before anything else, so a STOP during a slow entry refuses the send instead of queueing behind it (st-jm6u, §5.22). |
| POST | `/observe` | `{"spx": 6320.5}` | `{"spx": …, "fired": [...], "pending": [...]}` |
| POST | `/poll-fills` | `{}`; **JSON required** | `{"picked_up": [...]}` or `{"picked_up": [], "error": "..."}` |

**JSON required** (since 2026-09-01, audit finding 15): the three
state-changing routes that need no body refuse a request that does not carry
`Content-Type: application/json` (an empty `{}` body is fine) with a `400`. A
cross-origin HTML form post needs no CORS preflight and could otherwise fire
them from any page a browser on this box rendered; a form cannot produce the
JSON content type without a preflight the loopback never answers. `/stop` is
exempt by design — a hostile page firing it can only stop new risk, and
reaching it from a phone must not depend on a header.

Status codes: `200` acted or answered a read · `400` not a valid intent
(malformed, not refused), body `{"error": "bad_request", "detail": "..."}` ·
`409` a bound refused it, body `{"refused": {"bound": "...", "reason": "..."}}` ·
`502` the broker could not be reached, body `{"error": "broker", "detail": "..."}` ·
`404` no such route.

**Deliberately absent: `/unlock`, `/resume`, and any re-auth route.**
`tests/execd/test_api.py::test_the_url_map_holds_exactly_the_narrow_door` pins
the app's rule set to exactly these sixteen, and a second test names
`/unlock`, `/arm`, `/resume`, `/reauth`, `/re-auth`, `/oauth` explicitly. Adding
**any** route breaks the suite, not only an arming one. An agent that can reach this API can ask
the service to trade inside Steve's bounds. It cannot arm it, cannot clear his
STOP, and never sees the credential.

`ExecService` does have `unlock()`, `resume()` and `lock()` methods — they are
reached from Steve's page (`execd/page.py`, stage 3, §5.15), which is a
second Flask app on `127.0.0.1:8779`, published tailnet-only by
`tailscale serve`, and never from this API.

### 5.3 The status object

```
now, now_ct, sha,
arming:    {state, killed, kill_file, unlocked_at, expires_at, expires_at_ct,
            permits_entry, permits_exit}
day:       {open_positions, realized_loss_usd, attempts_used, attempts_left,
            loss_headroom_usd}
positions: [OpenPosition… — each with stop_order_id, stop_price,
            target_order_id, target_price, entry_spx and a valuation
            carrying at_stop_usd and at_target_usd]
loose_legs:        [{order_id, symbol, leg, qty, intent_id}] — bracket legs whose
                   position is closed and whose cancel is not confirmed (§5.22)
shorts:            [{symbol, qty}] — what the broker holds short on these instruments
unconfirmed_sends: [{intent_id, symbol, qty, limit, at, …}] — sends with no answer
foreign_orders:    [OrderResult…] — working buys this service did not send
foreign_positions: [{symbol, qty, avg_price}] — Steve's own legs, shown, never held
excluded_positions: {assetType: count} — what positions() left out
balances:  {available_funds, option_buying_power, buying_power, cash_balance,
            liquidation_value, error, as_of} — the account's money in Schwab's
            words (currentBalances.availableFunds, which its preview refuses an
            option buy against, and buyingPowerNonMarginableTrade), read at
            most every BALANCES_TTL_S = 15 s; on the trading page's foot and
            against the ticket before PREVIEW (Steve, 2026-09-15; st-shhi)
bounds:    {the thirteen bound values}
journal:   the path to today's file
```

The six lists after `positions` are the 2026-09-15 audit's rule that nothing
the account holds is silent (§5.22). Each is a line on the page's "in the
account, not this service's" card until it is gone.

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

There are **thirteen distinct bound names** — `armed`, `instrument`, `side`,
`order_type`, `qty`, `stop`, `protective_stop`, `window`, `positions`,
`ceiling`, `tick`, `price_band`, `preview_cost`. The table below has fifteen rows
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
| 7 | `window` | weekend; or before `open_ct`; or at/after `no_open_after_ct` — **not applied to SPX/SPXW roots** (`WINDOW_EXEMPT_ROOTS`; Steve 2026-09-14: "revoke the trading-hours rule when SPX is the target instrument. It can not fill after hours and placing live trades can help during testing"). Since those are the only instruments, the window gates no entry today; an unlock after the close arms until 23:59 CT instead of being refused |
| 8 | `positions` | `open_positions >= max_open_positions` |
| 9 | `ceiling` | `attempts_used >= max_attempts` — an attempt is a filled position, held while open and kept only if it closes at a loss; a close at break-even or better gives it back (Steve, 2026-09-14, st-fn5y, §5.20); a working entry holds a slot (row 8) but no attempt |
| 10 | `ceiling` | `realized_loss_usd >= daily_loss_ceiling_usd` |
| 10a | `tick` | the limit (or a stop price) is off the exchange's grid — 0.05 below $3.00, 0.10 at and above it (measured 2026-09-04, st-pohq); an off-grid price is a rejected order, not a tighter one |
| 11 | `price_band` | no quote; or quote older than `max_quote_age_s`; or not two-sided; or limit above `ask*(1+band)`; or limit below `bid*(1-band)` |
| 12 | `protective_stop` | no `$SPX` mark; or the stop sign is transposed (`stop_is_consistent` false); or the limit is too cheap for `protective_stop_price` to derive a stop at all |
| 12a | `ceiling` | the entry's own worst case — limit down to its derived stop, `check_risk_budget` — exceeds `daily_loss_ceiling_usd` minus loss already realized |
| 13 | `preview_cost` | the broker's preview total exceeds `max_cost_usd + preview_cost_tolerance_usd`; or the broker would not accept the order |

Steps 12 and 13 run inside `ExecService`, not `check_entry` — 12 in
`_protective_stop_refusal`, 13 in `_place_entry` after the broker preview.

**An exit clears four things only** (`check_exit`): the instrument, that the
side really is `SELL_TO_CLOSE`, — *only when the service knows the size* —
that `qty <= held_qty`, and that any price it carries is on the tick grid (an
off-grid stop is no stop, and refusing it cannot trap him). When `held_qty` is `None` the order goes through, because
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
7. Read the `$SPX` mark. Last look at the STOP file. Journal **`sending`**
   with the intent's shape, then `broker.place(intent)`. A `BrokerError` here
   journals `send_unknown` and holds the intent as **unconfirmed**: the broker
   may have taken the order, so every entry — this intent first of all — is
   refused `send_unconfirmed` until reconcile's orphan sweep (§5.22) has
   matched it to the listing or found nothing for `SEND_SETTLE_S`. On an
   answer, journal `placed` with the sha, the spx and the order.
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
one at the same price for what is left (`_book_close`, reached from `_settle`
and from `poll_fills`). `_rest_stop_at` is the **only** place a resting stop is
created, so its size can never drift from the position. Since st-fn5y the
resting take-profit beside it is resized in the same motion (`_rest_target_at`,
its mirror); the two are one bracket — §5.20.

A failure to rest the stop journals `stop_unprotected` — loud, because the
position is live and unprotected until the SPX-mark loop or Steve deals with it.

### 5.8 The journal

`execd/journal.py`. One `YYYY-MM-DD.jsonl` file per **Central** trading day
under `<state-dir>/journal/`. Every line is written, flushed and `fsync`'d
before the call returns.

Every line carries `ts`, `ts_ct`, `event`, `sha`.

Events: `request` · `refused` · `preview` · `placed` · `rejected` · `filled` ·
`stop_placed` · `stop_unprotected` · `target_placed` · `target_unprotected` ·
`stop_adjusted` · `target_adjusted` · `oversold` · `exit_triggered` ·
`exit_unfilled` · `closed` · `canceled` · `flattened` · `replayed` · `error` ·
`unlock` · `stand_down` · `lock` · `stop` · `resume` · `recovered` ·
`unreadable`. The five with `target`, `adjusted` and `oversold` are the
bracket's (st-fn5y, §5.20).

`unreadable` is not written — it is *synthesised on read* when a line will not
parse, which is what a kill mid-write looks like. Surfacing it as data rather
than raising means the rest of the day is still the audit.

**The day is derived, not remembered.** `day_state()` rebuilds
`open_positions`, `realized_loss_usd` and `attempts_used` by reading the file,
so a restart mid-session recovers the ceiling rather than resetting it.
`attempts_used` is the positions this service opened that are still open plus
its losing closes: a `filled`+`kind=entry` line holds an attempt until the
position's last `closed` line (`remaining_qty` falsy), and then the attempt is
kept only if the position's `pnl_usd` summed over its `closed` lines is below
zero. Steve, 2026-09-14 (st-fn5y): *"An 'attempt' is a 'filled position'. Any
attempt that breaks even or better doesn't decrement the counter."* A `working`
entry holds a position slot and no attempt; an adopted position holds a slot
and no attempt. A partial close debits the loss immediately but only frees the
position slot — and judges the attempt — when `remaining_qty` is falsy.
**Losses only debit the ceiling** — a winning trade does not raise it. That is
FD0's `Budget` semantics carried across unchanged; the attempts rule is the
one thing that changed, on his word.

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
| `daily_loss_ceiling_usd` | `500.0` (Steve, 2026-08-31, st-2j80 — was `100.0`) |
| `max_attempts` | `10` (Steve, 2026-09-14: "from 2 up to 10. the $500 limit remains as is"; the code default is still `2`) |
| `open_ct` | `"08:30"` |
| `close_ct` | `"15:00"` |
| `no_open_after_ct` | `"14:50"` |
| `weekdays_only` | `true` |
| `price_band_pct` | `0.10` |
| `max_quote_age_s` | `30.0` |
| `preview_cost_tolerance_usd` | `5.00` |
| `require_protective_stop` | `true` |
| `take_profit_multiple` | `10.0` (Steve, 2026-09-14, st-fn5y: "a 10x profit target") |
| `take_profit_basis` | `premium` — the target is the fill price times the multiple; `risk` makes it the fill plus the multiple times the distance to the stop. **ASSUMPTION: premium.** His ruling on which "10x" he means is pending on st-fn5y; change the basis in the file when he rules |

**An unknown key is a start-up error, not a silent default** — a typo must not
leave the service running under limits Steve did not choose. Validation also
rejects an empty `instruments`, `qty_cap < 1`, `max_open_positions < 1`, a
non-positive ceiling, `max_attempts < 1`, `price_band_pct` outside `(0,1)`, a
non-positive `max_quote_age_s`, `open_ct >= close_ct`, a `no_open_after_ct`
outside the window, a `take_profit_basis` other than `premium` or `risk`, a
non-positive `take_profit_multiple`, and a premium-basis multiple at or under
1 (fill × 1 is the fill — a sale, not a target). A file that exists but is
wrong **raises**; a file that is absent falls back to the start values.

**The ceiling bounds the position in front of it, not only the day behind it.**
Until 2026-08-31, `check_entry` refused a new entry once *realized* loss reached
the ceiling and never asked what the entry it was about to admit could lose, so
two attempts could each realize more than the whole day's ceiling with every
bound passing — finding 6 of case st-5qjq. `check_risk_budget` now prices the
entry at its limit, which is the most a buy can pay and therefore the most it
can lose, walks it down to the stop the entry would rest, and refuses if that
exceeds the headroom left. Checked against the *remaining* headroom, which is
what makes the sum of the day's worst cases fit inside the ceiling.

The same ruling raised the ceiling from $100 to $500. At $100 the bound could
never bind: a $2.10 SPX call with a twelve-point stop risks $205 whatever the
ceiling says, so the only entries that fit were ones too cheap to be real
trades. At $500, measured against the service's own stop arithmetic, a $2.10
call risks $205 and sends, a $5.00 call with a ten-point stop risks $400 and
sends, and an $8.40 call with a twenty-point stop risks $835 and is refused —
the same contract with an eight-point stop risks $400 and sends. The bound is on
the distance to the stop, not on the premium.

The *shape* of the bounds is not configurable. There is no key that switches a
bound off, because a bound you can switch off is not a bound.
`require_protective_stop` exists as a key only so the refusal has something to
name; setting it `false` is one of the conditions `problems()` raises on, so
such a file does not load. Until 2026-08-31 it did load, and it switched off the
one bound the design calls not optional — finding 8 of case st-5qjq.

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

`COMMISSION_PER_CONTRACT_USD = 0.65` — Schwab's published options rate; the
Schwab transport reads the preview's `projectedCommission` instead.

**`SchwabBroker`** (`execd/schwab.py`, stage 2). The same eight methods over
the Trader API and the market-data API, `httpx` with an access token in a
header. It holds no credential of its own: `bind(service.arming)` gives it
`Arming.credential` for the trading app, asked on every call, so a lock is a
lock on the transport. Each credential's payload is `{"app": {"key",
"secret"}, "token": <schwab-py wrapped>}`; the access token derived from each
is cached in memory per app and refreshed from that app's refresh token near
expiry, never written anywhere; past the seven-day wall it refuses before
calling. It sends GET, POST and DELETE and
never PUT (a source test keeps it so — the replace verb is how a chase would
sneak in). A GET meeting a 401 refreshes once and retries once; a POST meeting
one is reported, never repeated. `place` is a 201 with the order id in the
`Location` header followed by a read of the order (a 400 is a rejection,
returned, not raised; a 201 without a Location is held WORKING under a
synthetic id, which reconcile's orphan sweep identifies from the listing —
§5.22); `cancel` is a DELETE followed by the same read **repeated until the
status is terminal or `CANCEL_CONFIRM_S`** (6 s, twelve polls): Schwab's
DELETE is an ask, and a `PENDING_CANCEL` is an order the exchange still holds.
A leg still WORKING at the deadline comes back as such with the broker's word
in `message`, and the service treats it as not off (§5.22). Cancelling a stop
that already filled reports the fill. `positions()` admits a leg when its
**OCC root** is in `roots` — the bounds' `instruments` — and never reads the
account body's `underlyingSymbol`, which has never been recorded for an
option leg while every recorded order leg says `SPXW`; what it left out is
counted in `excluded_positions`, on `/status`. No token, key or account
identifier reaches a message; the account hash reads `<account>` in every
path quoted.

**Recorded versus spec-derived.** The market-data shapes were recorded live on
2026-09-04 (`tests/fixtures/schwab/`, `_capture.json`). The Trader API shapes
could not be: app 1 answered every `/trader` path with HTTP 401 `no apiproduct
match found` — the Accounts and Trading product was not on it — so account
numbers, positions, orders and preview are written to the API specification,
say so in their docstrings, and their test fixtures are marked `SPEC`.
`scripts/record_schwab_shapes.py` in full mode — that is, without
`--market-only` — re-records them against app 2; that re-run is the
acceptance for this part of stage 2. The recorder presents each app's own
bearer and picks by path through the service's own `app_for`, imported
rather than restated, so a shape cannot be captured through a different app
than the one that will read it live.

### 5.12a Two Schwab apps, chosen by the endpoint family (st-p9mx)

Steve has two registrations at developer.schwab.com and the split is permanent:
the portal **will not** add the Accounts and Trading product to app 1, so every
`/trader/v1` call on it answers 401 `no apiproduct match found` for good, and
app 2 holds that product. Confirmed by Steve 2026-09-05.

| | App 1 — market data | App 2 — trading |
|---|---|---|
| Serves | `/marketdata/v1` — quotes, chains, history | `/trader/v1` — accounts, preview, place, cancel, orders, positions |
| Env names | `SCHWAB_API_KEY`, `SCHWAB_APP_SECRET`, `SCHWAB_TOKEN_PATH` | `SCHWAB_TRADING_API_KEY`, `SCHWAB_TRADING_APP_SECRET`, `SCHWAB_TRADING_TOKEN_PATH` |
| Loader | `strader.settings.load_schwab_market` | `strader.settings.load_schwab_trading` |
| At rest | plain JSON, 0600, service state dir — `scripts/execd_market_credential.py` | encrypted vault under Steve's passphrase — `scripts/execd_vault_init.py` |
| In the service | held from start-up, outside arming | held by `Arming`; **LOCKED means it is not in memory** |
| Re-auth | `scripts/refresh_schwab_token.py` | `scripts/refresh_schwab_token.py --trading`, then the page at stage 3 |

**How a call picks its app.** `execd.schwab.app_for(path)` reads the request
path; there is no argument saying which app to use, because an argument is what
drifts. An unmapped family raises rather than defaulting, so a request family
added by hand next year stops on its first call instead of quietly borrowing
whichever credential was to hand. `tests/execd/test_schwab.py` pins the mapping
behaviourally — it watches which bearer token actually reached which path, so a
path computed at run time cannot slip past it.

**Why the market credential is allowed outside the vault.** This is the answer
to the design point st-p8k8 left open on 2026-09-04: the service comes back
LOCKED after every restart, but the 07:00 CT premarket jobs run before Steve is
awake to type a passphrase. The question was hard while one credential served
both families — a token left loadable without a passphrase was a token that
could place an order. With the split it is not: app 1 cannot trade, by Schwab's
enforcement rather than our promise, so holding it outside the lock costs no
capability. **`/quote` and `/chain` therefore answer while the service is
LOCKED, and every `/trader/v1` method still refuses.** Schwab's 401 is an
observation with a date on it rather than a guarantee, so the code holds the
same boundary independently and a test asserts it.

**Two grants, two seven-day walls — one sitting.** Each app has its own OAuth
grant and its own wall. Left alone they drift apart and become two re-auth days
a week in two different places. The rule is to renew **both** in one sitting
whichever one is due: renewing a still-valid grant costs nothing and resets its
clock, so one sitting a week holds both walls on the same day.
`broker.token_status()` reports both — the trading app at the top level, the
market app under `market` — and the page shows the nearer of the two. Each app's
re-auth is verified against the family it exists for: app 1 with a market-data
call, app 2 with `/trader/v1/accounts/accountNumbers`. Probing the wrong family
is the 2026-05-20 outage, in which a good market-data token was restored over
because the check hit `/trader/v1` and 401'd.

### 5.12 Recovery

`_recover()` runs in the constructor. It replays today's journal and rebuilds
`_open` from `filled`+`kind=entry`, `stop_placed`, `target_placed`, the legs'
`canceled` lines and `closed` lines (and `_working` from `working` lines,
with the page's `page_query`), then journals `recovered` if anything survived. The service comes back **LOCKED**, so
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
| 2 | `st-w2nw` | **built 2026-09-04**, trader shapes recorded 09-05 — the Schwab transport, the vault, the OAuth helpers the page calls (`authorize_url`, `code_from_received_url`, `exchange`, `refresh`, `verify_grant`). Left open only for the live read-only proof, which is stage 3's first unlock. |
| 3 | `st-p8k8` | **built 2026-09-13**, Steve's three lines pending — dedicated user, systemd unit, `deploy/install.sh --execd`, the page (§5.15), the readers re-pointed, the token-age heartbeat reading the service, the hook change presented. The plaintext token files retire once the service has been seen answering a morning run. |
| 4 | `st-k6gl` | one 1-lot live single with Steve at the STOP button |
| 5 | `st-47i2` | FD0 tickets and promoted rules become intents; the paste line retires |

**Order is strict. Nothing sends before stage 4.**

### 5.15 The page and the installed service (stage 3, st-p8k8)

**Where it runs.** `bash deploy/install.sh --execd` (Steve, as root) creates
the system user `execd`, copies the `execd/` package — only that package — to
`/opt/execd/execd` (root:execd 0750) with an `INSTALLED` stamp naming the
commit, builds `/opt/execd/venv` from `deploy/execd-requirements.txt`, seeds
`/etc/execd/bounds.yaml` once, writes `/var/lib/execd/market.json` from the
repo's market token (app 1), asks for the vault passphrase twice and writes
`/var/lib/execd/vault.json` (app 2), installs and starts
`strader-execd.service`, and runs `tailscale serve --bg --set-path /exec
http://127.0.0.1:8779/exec`. Re-running it refreshes the code and restarts the
unit; it never overwrites a bounds file, a vault or a market credential that
exists. `--dry-run` prints every step and touches nothing. The unit runs as
`execd` with `ProtectSystem=strict` and `ReadWritePaths=/var/lib/execd`, and
`installed_sha()` reads the stamp, so every journal line names the commit
that was installed.

**The page** (`execd/page.py`) is a second Flask app in the same process on
`127.0.0.1:8779`, reachable only through `tailscale serve` (tailnet, never
funnel) at `https://mydesk-1.tail89f676.ts.net/exec/`. One rule: every action
that adds capability takes the passphrase; every action that reduces it does
not.

| Action | Passphrase | What it does |
|---|---|---|
| UNLOCK | yes | opens the vault, arms until today's close (`ExecService.unlock`) |
| STOP | no | touches the kill file; one tap from a phone |
| clear STOP | yes | `ExecService.resume` |
| FLATTEN | no, but a second page with a single-use 60 s confirm | `ExecService.flatten` |
| stand down / lock | no | `stand_down` / `lock` |
| re-authorise (either app) | yes, twice: for the link and for the store | `authorize_url` → Steve logs in → pastes the landing address → `exchange` → `verify_grant` against the app's own family → stored: the trading grant back into the vault under the same passphrase (and swapped into memory if armed), the market grant to its file |

A wrong passphrase is journaled as `refused` with bound `passphrase`, costs a
one-second delay, and carries no value. A re-auth is journaled as `reauth`
with the app and its new wall. An unlock now journals the trading grant's
wall too, so the status object's `credential.last_known_trading_wall` can be
read while LOCKED — which is what the 06:30 token-age heartbeat gets.

**Why the passphrase and not a login.** Every agent shell on this box is root
and can reach the loopback port directly; a cookie or header is forgeable by
root, the passphrase is not held by any agent. The port is the second layer:
the hook change presented with this stage (`docs/patches/2026-09-13-gate-execd-runtime.diff`,
and its COO twin) denies agent shells the page port, writes under
`/opt/execd`, the install itself, Windows shells, memory readers, and stopping
the unit.

**The readers.** `broker_schwab.client.create_client()` returns
`broker_schwab.execd_client.ExecdClient` when the service answers on 8778 and
the old `schwab-py` client over the token file when it does not
(`STRADER_MARKET_DATA=execd|legacy|auto`). The client offers the four calls
the readers make — `get_quotes`, `get_option_chain`,
`get_price_history_every_minute`, `…_every_five_minutes` — over
`GET /marketdata/<kind>`. No consumer changed. The token-age heartbeat
(`scripts/schwab_token_health.py`) reads the service's walls first and the
files only as fallback. `reauthData` / `reauthTrade` answer with the page's
address once `/opt/execd/INSTALLED` exists.

---

### 5.16 The watcher (stage 4, st-k6gl)

`execd/watch.py`. Found while walking the full life cycle on 2026-09-14:
`POST /observe` (the SPX-mark exit) and `POST /poll-fills` (the fill sweep)
existed from stage 1 and **nothing in the tree called either one**. A fill
rested its broker stop and then sat unwatched by the accurate loop until the
next `place` or `flatten` happened to reconcile.

`Watcher` is a daemon thread started by `__main__` (`--watch-interval`,
default 5 s; `0` turns it off, trials only). Each pass: LOCKED → nothing (no
credential, no exit possible); no position and no working entry → nothing;
otherwise `reconcile()` (the broker's truth on fills and what closed), then
the index mark into `observe()`, which fires FD0's SPX-level exit. Every
5 s while exposed, every 30 s idle. A broker outage is one `error kind=watch`
journal line per outage and a `watch: broker back` line when it clears; an
unexpected exception is logged and the loop continues. It never opens
anything — `reconcile` and `observe` are exit-class.

Reaches the running service at the next install (`installExecd`).

### 5.17 Paper mode (stage 4, st-k6gl)

`execd/paper.py`. Steve, 2026-09-14: *"since schwab doesn't support paper
trading via api I'd like to simulate one by defining a mode where every api
submission is live except anything that submits a live order."*

**The mode file:** `/etc/execd/mode`, Steve's, one word: `paper` or `live`.
Absent means `paper`. Any other word and the service refuses to start. The
install seeds it as `paper` once and never touches it again. To go live:
write `live` there and run `installExecd` (a restart is what re-reads it).

**What paper does.** `PaperBroker` wraps the real transport. Quotes, chains,
the raw market reads, the account, the token walls and **the broker's own
preview** go to Schwab exactly as in live mode. `place`, `cancel`, `orders`,
`positions` and `fills_since` never reach Schwab: they run against a book at
`/var/lib/execd/paper-book.json`, filled against live quotes:

| order | paper behaviour |
|---|---|
| limit buy | fills at once at the live offer when the offer is at or under the limit; else rests and fills when the offer comes down to it |
| market sell | fills at once at the live bid |
| stop sell | rests; fills at the bid once the bid is at or under the stop price |
| cancel | resting → CANCELED; already filled → reported filled (the race) |
| any order with no live quote | refused — nothing is simulated without a market |
| the day after a contract's expiry | a resting order in it → CANCELED `expired`; a position in it → a SELL_TO_CLOSE fill at 0.00 (`paper-expiry-NNNN`), which the service books as an `external` close with its loss (st-ee8f) |

Order ids are `paper-NNNN`. Steve's real positions are invisible to the
service in paper mode, on purpose: paper must not adopt, watch or flatten
what it did not open. The book persists across a restart, and nothing in it
outlives its contract.

**What paper does not rehearse** (finding 33 of the 2026-09-15 audit): the
broker's *answers*. The book cancels synchronously, lists an order the
instant it is placed, stamps fills at the sweep, and cannot time out a send.
Every high finding of that audit lived in those answers, and §5.22 is what
the service now does about them; a paper cycle proves the loop closes, not
that the transport's assumptions hold.

**Every line says so.** `mode: paper` on every journal line, `mode` in
`/status` and in every `/preview` and `/place` answer, an amber PAPER
banner on the page, and the desk prefixes every read-back with
`PAPER (simulated) — `. The service's whole loop — rules, preview, the
protective stop, the watcher, reconcile, the fill sweep, FLATTEN — runs
unchanged over the book, so paper exercises the same code the live ticket
will. `tests/execd/test_paper.py` walks it.

### 5.18 The position's money on the page (stage 4, st-k6gl)

Steve, 2026-09-14: *"the unrealized pnl including all aspects of the order
needs to display on the page."* `ExecService.valuation(pos)` rides on every
position in `/status` and `_day_pnl()` as `pnl`:

| field | meaning |
|---|---|
| `cost_usd` | entry price × 100 × qty |
| `bid`, `ask`, `quote_age_s` | the live quote the value is struck at |
| `value_usd` | **bid** × 100 × qty — what a market sell gets now, not the mid |
| `unrealized_usd` | value − cost, before commissions |
| `entry_commission_usd` | from the broker's preview at the fill (published rate for a recovered position) |
| `exit_commission_usd` | published per-contract rate × qty |
| `commissions_usd` | both |
| `net_if_closed_usd` | value − cost − commissions — the number he asked for |
| `at_stop_usd` | the same arithmetic at the resting stop's price |
| `error` | why the money is blank when the quote could not be read |

`pnl`: `realized_usd` (the day's `closed` lines summed, gains positive),
`closes`, `unrealized_net_usd`, `day_usd`. The page renders an "Open
position" card with every row, green or red edge by the net, and reloads
itself every 5 s **only while a position or working entry exists**, so a
passphrase being typed on a quiet page is never wiped.

### 5.19 The order form — `/exec/order` (stage 4, st-k6gl)

`execd/orderform.py` (the selection, the chain read, the choice, the priced
ticket, the intent) and `execd/orderpage.py` (the HTML, one small inline
script). Steve, 2026-09-14: *"the page needed to run by code alone … a
button to indicate bearish or bullish intent … pre-populating the strikes
available … indicate a delta so I can over-ride the default … only the
essential elements of the order form … eventually this needs to run on an
iPad."* No model, agent or terminal between his intent and the service.

**The page, top to bottom** (refined 2026-09-15, st-shhi — Steve: *"stage
and submit orders without agent intervention … lots of redundant labels …
reference to reauth doesn't belong here … a bullish/bearish button and a way
to override the delta and reprice and send"*; design
`docs/design/order-page/`): **the strip** — the mode badge, the arming word,
the one ticking clock, STOP, and an *account* link — the same on every stage;
the stage card (§5.21) only when there is a stage to show; BULLISH / BEARISH
as two buttons; **the ticket** in three lines — what will be sent and its cost, the
cut and the resting stop's net, the target's net — with the derivation
behind *more*, and PREVIEW as the one action, in the upper portion of the
page (Steve, 2026-09-15); then the tuning — expiry chips, the **δ target** box (starts at
`DEFAULT_DELTA` = 0.80, Steve 2026-09-15 from his 08-19 words; a blank box
means nearest to spot) and RE-PRICE on one row, with FD0 budget and attempts
folded under *budget and attempts* — and the strikes around spot, the chosen
row marked; after a preview the card shows
Schwab's cost line and SEND; one line for the day.

**The padlock** (st-2s4u; Steve, 2026-09-15: *"the re-price button should
simply reprice existing strike. not force a new preview. the alternative is
to leave the price watcher live but give a control to lock price at current
allowing a submission at that price. this is how TOS platform works. a
padlock icon toggled between locked and unlocked"*): the ticket's price
follows the live ask — the poll returns `limit_now` (the ask on the tick
grid) and its cost, and the script writes them into the head — until the
padlock beside it is tapped. Locked, the price is frozen at the number that
was on the screen, the derivation is re-run at that price (the resting stop
and its net move with it), the live ask shows in small type beside it, and
PREVIEW sends it as the limit; the service's price band (§3) still judges it
at preview and at send. The lock is a hidden `limit` field on the form, so
the server renders the ticket from it and the script only flips the field;
without a script the ticket is priced at the ask when the page loads and
there is no lock. RE-PRICE now carries the tapped strike (before st-2s4u it
did not, and re-chose by delta) and its own field `reprice=1`, which means
*at the market* and drops the lock; a new strike, expiry, side or δ drops it
too; a cancel brings the form back at the market. On a PREVIEWED card,
RE-PRICE previews the same selection again at the market in one tap and
lands back on the card with a fresh SEND token — the broker's preview runs
underneath because SEND depends on it; it used to be a link back to the
unpreviewed form, two taps from SEND. The clock, the quote and the balances
tick on the fresh page again: the panel script returned early when there
was no stage card, which froze the page from the st-shhi change to this one. `/exec/` **is** this page
since st-shhi. Everything that is not placing an order — clear STOP,
stand down, lock, the weekly re-authorisation, the holdings that
are not this service's, the journal tail — is `/exec/account`, one tap away;
the strip's STOP and the card's FLATTEN carry `back=order` so their answer
lands back on the trading page. **Since st-2hei** (Steve, 2026-09-15: *"if
panel is locked the Passphrase should be displayed. way too many words in
execd screen … no need to define PAPER. Still don't need 'GRANTS' section.
Still looking for Options Buying Power amt"*): a LOCKED service puts the
passphrase box and UNLOCK on the trading page itself, under the strip, with
`back=order`; when the service is armed that same place carries *option
buying power* in bold with *available* beside it (the money line left the
foot — and while locked the account cannot be read, which is why the number
was missing); the `PAPER (simulated) —` prefix is gone from every answer,
the strip's badge is the word; the account page lost its PAPER/LIVE
definition lines, its explanatory sub-lines, the *Schwab grants* card, the
vault path and the URL footer — the state word, the buttons, *Today*, a
folded *re-authorise (weekly)* and the journal remain.

| Route | Does |
|---|---|
| `GET /exec/` | the trading page — the same render as `/exec/order` (st-shhi) |
| `GET /exec/account` | the account page: arming, STOP/clear, stand down, lock, re-authorisation (folded), holdings not this service's, the journal tail — no grants card since st-2hei |
| `GET /exec/order?side=call\|put&expiry=…&strike=…&delta=…&budget=…&attempts=…&limit=…&reprice=1&embed=1` | renders the page; `embed=1` drops the shell for a panel; a `delta` key present and empty means nearest to spot, absent means the 0.80 target; `limit` is the padlock's locked price, `reprice=1` (the RE-PRICE button's own field) drops it (st-2s4u) |
| `GET /exec/order/price?…` | the priced ticket as JSON plus the FD0, strikes and hidden-field fragments the script swaps in; a `limit` prices the ticket at that number instead of the ask |
| `GET /exec/order/state?symbol=…&lots=…` | the status body's live half plus the chosen contract's quote and the SPX mark, with HTML fragments; with a quote, `limit_now` (the ask on the tick grid) and `cost_now` for the head to follow while unlocked |
| `POST /exec/order/preview` | `service.preview(intent)`; on a 200, the cost line and a single-use 60 s SEND token; a `limit` in the body is sent as the intent's limit; the PREVIEWED card's RE-PRICE posts here again without one |
| `POST /exec/order/send` | spends the token, `service.place(the same intent)` with the selection query riding on the working entry, redirects with the result in words |
| `POST /exec/order/adjust` | UPDATE on the position card: `symbol`, `stop_price`, `target_price` (either may be blank) → `service.adjust`; redirects with what moved (§5.20) |
| `POST /exec/order/cancel` | CANCEL AND RE-PRICE on the working-entry card: `order_id` → `service.cancel`, then redirects to `/exec/order` with the side/expiry/strike/delta/budget/attempts the entry was priced from — never its lock — so the form comes back priced fresh (§5.20) |

**The choice** (`orderform.choose`): a tapped strike wins; else the delta
override picks the strike whose |delta| is nearest; else nearest to spot
(Steve's ruling). Ties go to the tighter spread.

**The chain read** (`orderform.load_chain`): one bounded `market_read("chains")`
per side and expiry — `strikeCount=40`, one `contractType`, `fromDate=toDate`
— parsed by the engine's own `parse_chain`, SPXW preferred; never the
unbounded `service.chain`. Answers while LOCKED (the market credential).

**The limit** is the ask rounded up on the service's tick grid
(`stops.tick_for`: 0.05 under $3, 0.10 at and above), so the `tick` rule
cannot refuse it. **The resting stop** shown is `protective_stop_price` at
that limit; its net includes both commissions.

**The intent** is `page-<stamp>`, source `page`, with `stop_spx` and
`delta` from the ticket — the same wire form the desk sends. The journal
shows who sent.

**No passphrase on SEND**: arming already happened; the token is single use
and dies in 60 s, and the service's price-band and quote-age rules refuse a
stale ticket regardless. Agents cannot reach the page port (gate 7).

**The script** (inline, no external assets): re-fetches `/order/price` when
delta, budget, attempts or lots change; polls `/order/state` every 3 s for
the quote, the position and the state; pauses while the tab is hidden. The
page works with the script off — every control is a link or a form.

**iPad**: `apple-mobile-web-app-capable` for Add to Home Screen, full-width
buttons, tap-sized strike rows, `inputmode` numeric keyboards, no keyboard
shortcuts, nothing loaded from the network.

**Load, stated:** compose is microseconds; the chain is fetched only on a
side or expiry change; the poll is two small quote calls every 3 s per open
page. Unmeasured: Schwab's market-data rate limit (commonly cited 120/min;
this sits well under it) and Flask's dev server under an all-day poll.

`tests/execd/test_orderform.py` walks side → strikes → FD0 → preview → send
→ fill → stop over the real routes and the mock, including a stale token, a
refused preview, LOCKED, paper mode, the embed variant, and no secret in any
page or JSON body.

### 5.20 The bracket — take-profit, one-cancels-the-other, the live editor (st-fn5y)

Steve, 2026-09-14: *"Future filled orders will result in resting 'take
profit' orders in addition to stoplosses. The screen should be a live editor
allowing an update to both trigger conditions."* *"Upon fill, api should
create a resting order at a 10x profit target."* *"An 'attempt' is a 'filled
position'. Any attempt that breaks even or better doesn't decrement the
counter."* On a cancelled working entry: *"Assume the canceled order will be
re-priced and re-armed."* Four rulings, one change.

**The target.** On every fill, after the protective stop, the service rests a
SELL_TO_CLOSE LIMIT at the take-profit price (`_place_take_profit` →
`_rest_target_at`, the mirror of `_rest_stop_at` and the only place a target
is created). The price is `stops.take_profit_price`: on the `premium` basis
the fill times `take_profit_multiple` (a $2.10 fill → $21.00); on the `risk`
basis the fill plus the multiple times the distance to the stop ($2.10 with a
$1.50 stop → $8.10). Rounded **up** to the tick in force at the target. The
basis is a bounds key (§5.10); **premium is the ruled basis** (Steve,
2026-09-15: "10x means ten times the fill premium"; the ask on st-fn5y is closed). `OpenPosition`
carries `target_order_id` and `target_price`; the journal writes
`target_placed` (order id, price, basis, multiple, reward) and, when the target
cannot be derived or the broker refuses or rejects it, `target_unprotected` — a
**warning, not a fault**: the stop still stands. A target the bid is already
through when it lands fills at once, and that fill is the exit, booked as
`target`. Recovery (§5.12) rebuilds the target from `target_placed` the way it
rebuilds the stop, and clears a leg whose `canceled` line was not followed by
a new placement (a close was in flight when the service died).

**One cancels the other, by the service's hand.** Schwab's own OCO is not
something this service sends; it works the pair itself. When either leg
fills — the fill sweep, or a cancel that reports FILLED — the other comes off
**before** the `closed` line is written (`_book_close`), because every moment
it rests past the fill is a moment it can fill too. The `closed` line is
written either way: a cancel that fails is caught and journaled. A cancel that
finds the other leg *also* filled books that fill against what was still held
and journals anything past it as `oversold` — loud, because it is a short on
a long-premium-only account that this service, which only sells to close,
cannot itself buy back. `_market_close` (the SPX-mark exit, FLATTEN) takes the
stop and then the target off before its close goes on (`_take_bracket_off`);
a cancel that finds a leg filled settles on that fill and sends nothing; a
broker that cannot be reached at a cancel sends nothing, leaves what still
rests standing and puts back a stop that had already come off (DEFERRED); a
rejected or unsendable close re-rests both (`_rest_bracket`). A partial exit
resizes both. `flatten` pulls both. `cancel` refuses either leg's order id
(`protective_stop`, `take_profit`) — the bracket is edited, never pulled apart.
The `closed` line's `kind` is `target` when the target filled, `resting-stop`
or `protective-stop` when the stop did.

**The live editor.** `ExecService.adjust(symbol, stop_price=, target_price=)`
— `POST /adjust` on the API, UPDATE on the order page's position card (two
inputs pre-filled with the resting prices, `inputmode=decimal`, one button).
Exit-class: legal while STOPped or stood down, needs a credential. Each price
given is checked, and the refusal is named: `position` (nothing open in that
contract), `exit_in_flight` (the bracket is off while a close works), `tick`
(off the grid), `bracket` (a stop not below the live bid, a target not above
it — either would fill at once), `ceiling` (a stop moved so wide that the
position's risk to it exceeds the day's headroom — the ceiling doing to an
adjusted stop what `check_risk_budget` does to an entry; tightening never meets
it). A move is the same motion every other path uses — cancel the leg, rest a
new one (there is no replace-order; the transport has no PUT). A cancel that
finds the leg already filled books that fill and refuses the adjust as
`filled`, with what happened. A new price the broker will not rest brings the
old leg back. **Moving the stop moves the SPX-mark trigger with it**: the new
`stop_spx` is the entry's delta walked backwards from the level the entry
filled at (`_stop_spx_for`, the inverse of `stops.premium_at_stop`), so the
two stops stay one stop; the journal line `stop_adjusted` carries old and new
for both, `target_adjusted` for the target. The page's poll leaves the
position card alone while one of its inputs has focus, so a number half-typed
is never wiped. The status JSON carries `target_price`, `target_order_id` and
the valuation row `at_target_usd` (the same arithmetic as `at_stop_usd`).

**Attempts count losing fills only.** §5.8. Ten `max_attempts` are ten losing
positions; a winner or a scratch gives its attempt back; a working entry
holds a slot and no attempt.

**An unchanged leg stays; UPDATE once; best and worst** (st-ff5j, Steve
2026-09-15 14:07 CT: *"Stop moved from 10.30 to 10.30 … the running total
showed price at +70 but market order not fired … what's journal show?"*).
The page's UPDATE posts both boxes, so a leg whose box he did not touch
arrives at the price it already rests at; `adjust` leaves that leg alone —
no cancel, no re-rest, a journal line `adjust_unchanged` and the answer
*Stop unchanged at 10.30* — because a cancel-and-re-rest of an unchanged
stop is a moment with no stop resting and two broker round trips for
nothing (it happened twice in that minute). The UPDATE button goes dead the
moment the form leaves (*UPDATING…*), so a second tap while the first
adjust is at the broker is not a second adjust. And every position keeps
the best and worst `net_if_closed_usd` it has shown, with the time of each,
struck from the valuations the status body computes — so they move while
the page's poll is reading, every few seconds while he watches; in memory
only, a restart starts them again. They sit under NET NOW on the filled
card, as a *best · worst* row on the CLOSED card, and in the `closed` line
(`best_net_usd`, `best_at`, `worst_net_usd`, `worst_at`), so the record can
answer "how far did it go my way before the stop took it". The take-profit
is a resting limit at a *price*; NET NOW is what a market sell nets *now*;
nothing fires at a dollar figure.

**Cancel and re-price.** A working entry on the order page carries one button,
CANCEL AND RE-PRICE. The page stored the selection query the entry was priced
from on the `WorkingEntry` at send time (`page_query`, on the `working` journal
line, recovered across a restart, never part of the intent and never sent to
the broker); the cancel goes through `service.cancel`, and the redirect lands
on `/exec/order` with that query, so the form comes back priced fresh, ready
to PREVIEW and SEND. An entry the desk or the API sent has no query and lands
on the bare form.

`tests/execd/test_bracket.py` is what all of this has to mean: the arithmetic
on both bases, the target on the fill and at reconcile, the warning branches,
OCO both ways, both legs filled, both cancels before the close, every failure
branch putting both back, partial exits resizing both, the guarded cancel,
every adjust refusal, a leg that filled before it could move, the moved SPX
trigger for a call and a put, the API's four status codes, recovery, the
attempts rule through the service, the paper book's target fill, and the
page's editor and cancel.

### 5.21 The status panel — one card, seven stages (st-4ezg)

Steve, 2026-09-14, reviewing `/exec/order`: *"the complete status of the
order, plus controls to alter or refresh its rendering … optimize for the
obvious … the panel can re-size according to context."* COO drew it as a
design canvas (`docs/design/order-status-panel/`, seven artboards from one
template, revised twice on his review); on 2026-09-15 ("install is fired.
let's code the bracket") it became code: `execd/panel.py`, the card at the
top of the order page, replacing the state card, the preview card and the
position card that were there.

**The stage is read, never kept.** `panel.stage_of` looks at the status body
and the day's journal (`panel.journal_facts`: when each working entry was
sent, when each close went out, when each position filled, the last `closed`
line) and names one of seven: `none` (nothing held, nothing working),
`working` (an entry rests at the broker), `filled` (a position, no close in
flight), `exiting` (a close is in flight — the word on the card is SELLING),
`closed` (nothing live, a `closed` line today). Two stages belong to the
request, not the service: `previewed` (a PREVIEW just came back, the SEND
token is live) and `refused` (the page has a refusal to show). Those two never
hide money that is live — a preview while a position is held or an entry
works renders the ticket *above* the live part under the PREVIEWED word; a
refusal while something is live is the red box above the card and the card
keeps its stage and its controls.

**What each stage shows** (the detail rows fold under `less`):

| stage | title line | the big number | detail | controls |
|---|---|---|---|---|
| no order | nothing held, nothing working | — | last close, today's attempts and headroom | none |
| PREVIEWED | `C7630 × 1 · buy limit 4.70 = $470.00` | the broker's cost line | rules, SPX cut, most this costs, the stop and target that will rest | SEND (the nonce, once), RE-PRICE (previews the same strike again at the market, one tap — st-2s4u) |
| WORKING | `… · buy limit 4.70 · sent 12 s ago` | ask above the limit, `+0.05` | on fill (the SPX cut, the target multiple), the order id | CANCEL AND RE-PRICE — no STOP on a resting order |
| FILLED | `… · in 4.70 · 1 m 35 s ago` | NET NOW — a market sell after both commissions | bid/ask, quote age, SPX and the cut; the editor: stop and target inputs with the net at each | UPDATE, FLATTEN, STOP |
| SELLING | `… · in 4.70 · selling` | market sell sent, `4 s ago` | reason, stop · target cancelled, the order id | FLATTEN AGAIN |
| CLOSED | `… · closed 40 s ago` | P&L, commissions in | in → out and the hold time, reason, today's line | NEW ORDER |
| REFUSED | the refusal, in the service's words | — | — | RE-PRICE |

**The rules from the review, in every stage.** One clock, in the header,
Central time, ticking; every other time on the card is *x ago* and ticks too
(`<span class=ago data-at=…>`, the server's reading in the text and the
instant in the attribute). A contract is `C7630` / `P7600`
(`panel.contract_name`, off `parse_occ`; a symbol that is not OCC comes back
trimmed). One net number — the same `net_if_closed_usd` as the position row,
never gross with a footnote. No footers: the card is as tall as its stage.
PAPER or LIVE is a badge beside the stage word. STOP IS ON and *locked —
unlock on the operations page* are one line inside the card when they apply.

**The script.** Server-rendered, so the card works with no script — every
control is a form or a link. The script ticks the clock and the *ago* spans
once a second; polls `GET /exec/order/state` every `POLL_S` seconds and swaps
the body (`panel_body_html`, with `panel_stage` for the header word) unless
an input on the card has focus, the page is hidden, the card is paused, or
the card is in a request-owned stage (a poll would erase the SEND token);
*pause*/*resume* stops and restarts that with the *updated* stamp saying
`paused`; the refresh button polls now regardless; *more*/*less* toggles a
`compact` class that hides the `.full` rows, remembered in `localStorage`.

`tests/execd/test_panel.py` — the names and the units, the stage off the
service, every stage's card on the page, the two request-owned stages against
live money, the polled body never carrying a request-owned stage, every
action on the card an absolute `/exec/` path, no secret on the card.

### 5.22 The second audit's six (2026-09-15, Auditor case co-66wtd)

Fifteen days after the first verdict a blind verifier read stages 2–4 and
returned findings 23–44. Six blocked the first live ticket; five are code
here and the sixth is a paper cycle on the installed build with Steve's
passphrase (st-ee8f). Each is a rule now, tested by name:

| bead | rule | where |
|---|---|---|
| st-jm6u | **STOP takes no lock.** The kill file is touched before anything else; the journal line and the status read never wait on the service lock, so a STOP from the page during a slow entry refuses the send. | `ExecService.stop`; `test_audit_tail.py::TestStopHasTheLastLook` |
| st-zm2u | **Positions are admitted by OCC root**, never by the account body's `underlyingSymbol`, which was never recorded for an option leg while every recorded order leg says `SPXW`. `excluded_positions` is on `/status`. | `SchwabBroker.positions`; `test_schwab.py` |
| st-7ah8 | **A cancel is an ask.** The transport re-reads until terminal or 6 s. A leg still WORKING is not off: `cancel_pending`, the close DEFERs with the bracket resting; `_cancel_leg_quietly` keeps the id; a booked close that cannot confirm a leg carries it as a **loose leg** (`leg_unconfirmed` → `leg_resolved`, on `/status`, rebuilt on restart) that every reconcile re-asks and books `oversold` if it filled. **Shorts** are journaled `short_held` and shown; a sell on a symbol not held is `unattributed_sell`; a sell on a held symbol from an order not this service's is an `external` close; a FILLED order with no quantity books its own size, never the position's. | `service.py` `_pull_leg`, `_book_close`, `_reconcile_loose_legs`, `_reconcile_positions`, `_pick_up_fills`; `test_bracket.py::TestCancelIsAnAsk` |
| st-xlz9 | **A send is journaled before it goes out** (`sending`); one with no answer (`send_unknown`) holds every entry refused `send_unconfirmed` until the **orphan sweep** matches it to the listing (`send_resolved found` → the working entry or the position) or finds nothing for `SEND_SETTLE_S` (`not-found`, re-sendable). The sweep also identifies an `unnamed:` entry (`working_identified`) and journals any other working buy on these instruments once as `foreign_order`, shown, never adopted. | `_place_entry`, `_entry_refusal`, `_reconcile_orphans`; `test_reconcile.py::TestASendWithNoAnswer` |
| st-isx3 | **Adopt only what this service tried to open** — a contract with a `sending`, `working` or `filled` line in the last seven journal days. Everything else the account holds long is Steve's: `position_foreign` once, `foreign_positions` on `/status`, a line on the page's "in the account, not this service's" card, never slotted, never flattened; FLATTEN's confirm page names what it will sell and what it will not. | `_owned_symbols`, `_reconcile_positions`; `page._render_not_this_services`, `_render_confirm_flatten`; `test_reconcile.py::TestTheBrokerIsTheAuthorityOnPosition`, `test_page.py::TestNotThisServices` |
| st-ee8f | **Nothing in the paper book outlives its contract** (§5.17). The paper cycle itself is Steve's to unlock: the two 09-14 cycles ran `5ef0c02`/`28b566f`, before the bracket, the watcher exit, the order page and the panel. | `PaperBroker._expire`; `test_paper.py::TestExpiry` |

Still open from the same verdict and carried by name: Exit Settle Window
(st-b7i4, findings 26–27), Fresh Mark Before Send (st-xv5e, 32), Page Post
Guards (st-sk9r, 36), Bracket Past The Close (st-btob, 38), Reconcile Leg
Ids (st-vqmr, 39), Risk Budget Sums Open (st-s2jj, 40), Wall Test Remaining
Three (st-10da, 42), Runtime Gate Spellings (st-d1bo, 34/43), Patch Sidecars
Say Prepared (st-9q41, 44). The case, the evidence and the findings are at
`justSteve/Auditor` under `cases/co-66wtd/`.

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

**On the page** (stage 3, §5.15, the path of record once the service is
installed): `execd.schwab.authorize_url` builds the login link,
`code_from_received_url` takes the pasted redirect (and refuses a state that
does not match the link shown), `exchange` trades the code for a wrapped
token with `creation_timestamp` = now — the start of the seven-day clock —
`verify_grant` proves it against the family the app is for, and the page
stores it: the trading grant in the vault with the passphrase Steve just
typed, the market grant in its file. `refresh` renews the access token and
preserves the timestamp. Both apps, one sitting, so the two walls stay on the
same day. The script above keeps working only until the service is installed;
after that it answers with the page's address (`SCHWAB_REAUTH_FORCE_FILE=1`
overrides, for a fallback nobody should need).

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

1. **The broker library has no write path as shipped.** The repo's copy of
   schwab-py is a fork with `place_order`, `replace_order`, `cancel_order`,
   `preview_order` and every account and transaction call removed, and — since
   2026-09-01, st-c1af — the generic `_post_request` / `_put_request` /
   `_delete_request` methods removed as well; they had zero callers and let
   any holder of a `Client` issue an arbitrary authenticated request, which
   made the old "unrecoverable from within this codebase" claim true of the
   method table but not of the capability (audit st-5qjq, request 3). The
   authenticated session object still exists, so this layer raises effort and
   visibility rather than making an order impossible; the DEFENSE NOTE in
   `lib/schwab-py/schwab/client/base.py` now says exactly that.
2. **The gate key.** Any live Schwab client refuses to build unless
   `~/.schwab_gate_key` exists (`broker_schwab/client.py:31-36`) — a file only
   Steve creates. Stated honestly (audit st-5qjq, finding 18): the key has
   existed since 2026-05-21 because the live read feed depends on it, so this
   layer is in its permissive position and stops nothing while that is true.
   It is a layer against accidental client construction on a box where the
   key has been removed, not a standing barrier on this one.
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
- `FORBIDDEN_TRANSPORTS = {httpx, requests, urllib3, socket, aiohttp, urllib,
  http, http.client, ftplib, telnetlib, xmlrpc}` with **one exemption by file
  name and library name**: `TRANSPORT_MODULE = "schwab.py"`, `TRANSPORT_ALLOWED
  = {httpx}`. Every other module still imports no transport; a test asserts the
  exempted module really imports `httpx`, so the exemption cannot outlive the
  file it names; and a test imports every module and asserts the only broker
  classes are `MockBroker` in `broker.py` and `SchwabBroker` in `schwab.py`.
  `urllib` stays banned as a whole root even in `schwab.py`.
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
- **No general client for execd.** The desk's `DeskExecd` (§3.11) makes two
  calls, chain and preview; the readers' `ExecdClient` makes the market reads.
  Everything else — cancel, flatten, stand down — is Steve's page or `curl`.
- **No `place` from the desk.** `go` previews through execd (§3.11) and
  cannot send; routing `place` is the live half of stage 4, then stage 5.
- **No `vertical` or `condor` pricing**, though both are in the `Vehicle` type.
- **No TOS fixtures**, so every paste shape reports `inferred`.
- **No recorded preview, place or cancel shapes in execd.** Account numbers,
  orders and order-by-id were recorded 2026-09-05; the preview body records
  itself (`preview_raw`) at the first in-window preview after the next
  install (§3.11); place and cancel record at the first live ticket.
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
