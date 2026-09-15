# execd — the live execution service

The one holder of the broker credential on this box. Steve ruled the wall
crossing on 2026-08-30 (st-l3s4): *code executes live trades against the API,
the token is hidden from agents, pasting is not the long-term transport.*
This is that service. Epic **st-5qjq**; design of record
`docs/a2a/2026-08-30-coo-to-strader-live-execution-service-plan.md`.

**Stages 1, 2 and 3 are what is here.** Two brokers: `MockBroker` (stage 1,
st-eznu) and `SchwabBroker` (stage 2, st-w2nw) — the Trader API over plain
HTTPS in `execd/schwab.py`, the one module in the package that imports a
transport. There is no plaintext credential on disk here (the vault holds
the trading one, encrypted; the market one — which cannot trade — sits 0600
in the service's own state directory) and no import of the repo's hobbled
`schwab` library — `tests/execd/test_wall.py` asserts all of it by reading
the source and by watching what a full import actually loads. Stage 3
(st-p8k8) added the page (`execd/page.py`), the installed service
(`deploy/install.sh --execd`, `deploy/systemd/strader-execd.service`) and the
raw market-data door the repo's readers now use.

**Recorded, and not.** The market-data shapes were recorded live on
2026-09-04 and the Trader API read shapes — account numbers, the account
body, orders, order-by-id — on 2026-09-05 once app 2 had its grant
(`tests/fixtures/schwab/`). Preview, place and cancel are POST/DELETE, which
the recorder never sends by Steve's 2026-08-30 ruling; those shapes are
spec-derived until stage 4 sends the first one.

## Stage 3 — the installed service and the page

```bash
bash deploy/install.sh --execd            # Steve, as root; asks for the vault passphrase once
bash deploy/install.sh --execd --dry-run  # anyone: prints every step, touches nothing
```

The install creates the system user `execd`, copies this package (only this
package) to `/opt/execd/execd` with an `INSTALLED` stamp naming the commit,
builds `/opt/execd/venv` from `deploy/execd-requirements.txt`, seeds
`/etc/execd/bounds.yaml` once, writes `/var/lib/execd/market.json` from the
repo's market token, writes `/var/lib/execd/vault.json` from the trading
token under the passphrase Steve types, installs and starts
`strader-execd.service` (user `execd`, `ProtectSystem=strict`), and publishes
the page with `tailscale serve --bg --set-path /exec http://127.0.0.1:8779/exec`.
Re-running it refreshes the code and restarts the unit and never overwrites a
bounds file, a vault or a market credential that exists.

**The page** — `https://mydesk-1.tail89f676.ts.net/exec/`, a second Flask app
in the same process on `127.0.0.1:8779`, tailnet only, funnel never — holds
what the API deliberately lacks. One rule: every action that *adds*
capability takes the passphrase (UNLOCK, clear STOP, store a re-authorised
grant); every action that *reduces* it does not (STOP, FLATTEN with a
single-use confirm, stand down, lock). The weekly re-authorisation of both
Schwab apps runs there: the page shows the login link, Steve pastes the
landing address, the service exchanges the code, proves the grant against the
app's own family (`verify_grant`) and only then stores it — the trading grant
back into the vault, the market grant to its file, and into memory if the
service is armed. Nothing on the page, in the journal or in a log line ever
carries a passphrase or a token.

**The readers.** `broker_schwab.client.create_client()` returns an
`ExecdClient` when the service answers on 8778 — the same four `schwab-py`
read calls, over `GET /marketdata/{quotes,chains,pricehistory}` — and the
old token-file client when it does not. No consumer changed. The token-age
heartbeat reads the service's walls first. Once a morning run has been seen
going through the service, the token files under `tokens/` retire and
`reauthData` / `reauthTrade` already answer with the page's address.

**Presented, not landed:** `docs/patches/2026-09-13-gate-execd-runtime.diff`
(and its COO twin) deny agent shells the six ways round the process boundary
the design names — writes under `/opt/execd`, the install, Windows shells,
memory readers, the page port, stopping the unit. Hooks are Steve's to land.

---

## Run it

```bash
.venv/bin/python -m execd --mock --state-dir /var/lib/execd --mock-unlock
.venv/bin/python -m execd --schwab --vault /etc/execd/vault.json --state-dir /var/lib/execd --unlock-stdin
```

A broker flag is required, and its absence is a refusal rather than a default:
a process called `execd` that started quietly and turned out to be talking to
nothing — or to the wrong thing — would be worse than one that will not start.

`--mock-unlock` arms the mock with a fake credential so the API can be
exercised locally. It cannot arm the real broker: the guard is on the broker
object, not the flag order. `--schwab` comes up **locked** and stays locked
until Steve's passphrase opens the vault — on the tailnet page in stage 3, or
until then with `--unlock-stdin`, which reads it from standard input at the
console and never from argv or the environment. `scripts/execd_vault_init.py`
writes the vault from today's `.env` and token file; it asks for the passphrase
twice and is Steve's to run.

It binds `127.0.0.1:8778` and refuses to bind anything else.

```bash
.venv/bin/python -m pytest tests/execd -q      # the whole acceptance, no network
```

## The narrow door

Sixteen routes on the loopback, JSON in and out. `200` the service acted,
`400` the request was not a valid intent, `409` a bound refused it —
`{"refused": {"bound": "...", "reason": "..."}}` — `502` the broker could not
be reached.

| | |
|---|---|
| `GET /status` | arming state, the day's headroom, open positions, the bounds in force |
| `GET /quote?symbol=` · `GET /chain?root=` | market data through the service, so nothing else needs a credential |
| `GET /orders` · `GET /positions` · `GET /journal?n=` | what the broker holds, what the service tracks, what it recorded |
| `POST /preview` | price an intent through every bound, transmit nothing |
| `POST /place` | the one path that transmits |
| `POST /cancel` · `POST /flatten` | getting out |
| `POST /adjust` | move the resting stop, the resting take-profit, or both, under a live position — `{symbol, stop_price?, target_price?}` (st-fn5y) |
| `POST /stand-down` · `POST /stop` | done for the day; the kill switch on |
| `POST /observe` · `POST /poll-fills` | feed it the SPX mark; pick up a stop that fired — driven in-process by `execd/watch.py` since stage 4 (every 5 s while a position or working entry exists) |

| `GET /marketdata/<kind>` | the raw Schwab body for `quotes`, `chains` or `pricehistory`, query allow-listed to that resource's own parameters — the readers' door (stage 3) |

**The trading page** (`execd/orderform.py` + `execd/orderpage.py`, stage 4; refined 2026-09-15, st-shhi, design `docs/design/order-page/`): `/exec/` and `/exec/order` — one strip (mode, arming word, one clock, STOP, an *account* link), BULLISH/BEARISH, expiry chips with the δ target (starts at 0.80; blank = nearest to spot) and RE-PRICE on one row, the strikes around spot with bid/ask/delta, the ticket in three lines with the derivation behind *more* — its price follows the live ask until the padlock beside it is tapped, then it is frozen and PREVIEW sends that number (st-2s4u; RE-PRICE keeps the tapped strike and reprices at the market; on a previewed card it previews the same strike again in one tap), PREVIEW then SEND with a single-use token; unlock, clear STOP, stand down, lock and the weekly re-authorisation live on `/exec/account`, never on the trading page; the engine is `execd/compose.py` (moved from `strader/execution/`, which re-exports it). Manual §5.19. Since st-fn5y the position card carries the bracket's live editor — the stop and the target in two inputs, one UPDATE button — and a working entry carries CANCEL AND RE-PRICE, which pulls it and brings the form back priced from the selection it was sent from. Manual §5.20. Since st-4ezg the top of the page is **the status panel** (`execd/panel.py`): one card that changes shape with the order's stage — no order, PREVIEWED, WORKING, FILLED, SELLING, CLOSED, REFUSED — read off the status body and the day's journal; one ticking CT clock in the header and every other time *x ago*; contracts named `C7630`; one net number, commissions in; the filled stage is the bracket editor with FLATTEN and STOP; `more`/`less` folds the detail rows. Manual §5.21.

**Paper mode** (`execd/paper.py`, stage 4): `/etc/execd/mode` says `paper` (the
default, seeded by the install) or `live`. In paper every read and the broker's
preview are live; `place`/`cancel`/`orders`/`positions`/`fills_since` run
against a book at `/var/lib/execd/paper-book.json` filled against live quotes.
`mode` is on every journal line, in `/status`, in every preview/place answer,
and on the page.

**What is deliberately absent: `/unlock`, `/resume`, and any re-auth route.**
An agent that can reach this API can ask the service to trade inside Steve's
bounds. It cannot arm it, cannot clear his STOP, and never sees the credential.
That claim is asserted against the app's own URL map, so adding a route back
breaks the suite. Those three live on the page (stage 3), behind the passphrase.

## What it refuses, whatever the caller asks

`execd/bounds.py`, in the order the checks run. Start values in
`bounds.example.yaml`; `/etc/execd/bounds.yaml` is Steve's to edit.

| bound | start value |
|---|---|
| `instrument` | SPX / SPXW options only |
| `side` | opens are BUY_TO_OPEN — long premium only |
| `order_type` | entries are LIMIT; a market entry is a blank cheque |
| `qty` | 1 contract |
| `stop` | the STOP file blocks entries |
| `protective_stop` | an entry must carry `stop_spx` and `delta`, and the sign must not be transposed |
| `window` | 08:30–15:00 CT, weekdays; nothing opens after 14:50 |
| `positions` | 1 open at a time |
| `ceiling` | $500 realized loss, 10 attempts (2 at the design; 10 by Steve, 2026-09-14) — an attempt is a filled position, held while it is open and kept only if it closes at a loss; a close at break-even or better gives it back (Steve, 2026-09-14, st-fn5y). Rebuilt from the journal, so a restart does not reset it; and the entry's own worst case, limit down to its derived stop, must fit the headroom left — as must a stop moved wider by `adjust` |
| `bracket` | an adjusted stop must sit below the live bid and an adjusted target above it, on the tick grid; a leg that filled before it could be moved is booked and the adjust refused (`filled`) |
| `tick` | a limit or stop price on the exchange's grid — 0.05 below $3.00, 0.10 at and above (measured, st-pohq); off-grid is a rejected order, and an off-grid stop is no stop |
| `price_band` | a limit within 10% of the touch, against a quote under 30s old |
| `preview_cost` | the broker's own preview must agree with the intent before anything is sent |

An intent is idempotent by `intent_id`: a repeat is answered from the journal
and never re-sent.

## Three asymmetries, each with a test

**Entries are hard, exits are easy.** An exit clears three checks — that the
contract is one this service trades, that the side really closes, and that it
is not larger than the position (selling more than you hold is an opening sale
wearing an exit's label). Nothing that exists to keep Steve out of risk may
keep him in it, so `flatten` works while STOPped, while stood down, after the
bell and with the ceiling breached. An exit for a contract the service is not
tracking is sized against the broker's own position; only when the broker
cannot be reached at all does the order go through unsized, journaled as
`exit_unverified`, because refusing on ignorance is how an exit gate traps
someone. The one thing that refuses an exit is having no credential to send it
with.

**A fill without a protective stop is a state this service does not reach
quietly — and every fill rests a bracket.** The stop's inputs are checked
before the entry is previewed. On the fill the service derives the option-price
stop from the SPX level through delta (`execd/stops.py`) and rests it at the
broker, so a dead box still has a stop; beside it, since st-fn5y (Steve,
2026-09-14: *"future filled orders will result in resting 'take profit' orders
in addition to stoplosses"*), it rests a sell limit at the take-profit target —
the fill price times `take_profit_multiple` on the `premium` basis (a $2.10
fill rests a sell at $21.00), or the fill plus the multiple times the distance
to the stop on the `risk` basis; premium is the ruled basis (Steve, 2026-09-15:
"10x means ten times the fill premium"). The two are one bracket and the service works the one-cancels-the-other
itself: when either leg fills, the other comes off before the close is booked;
a cancel that finds the other leg already filled books that fill against what
was held and journals anything past it as `oversold`. While the box is alive
`observe(spx)` runs the accurate SPX-mark exit. A broker that refuses the
resting stop is journaled as `stop_unprotected` — loud, because the position is
live; a target that cannot be derived or rested is `target_unprotected` — a
warning, because the stop still stands. When an exit fills only partly, both
resting legs — sized for the whole position — are cancelled and re-rested at
the smaller size, because a leg larger than the position would sell contracts
Steve no longer owns. Both legs are edited from the page, never pulled apart:
`cancel` refuses either leg's order id, and `adjust` moves either by the same
cancel-then-rest motion (there is no replace-order; the transport has no PUT),
refusing a price off the grid, a stop not below the live bid, a target not
above it, or a stop moved wider than the day's headroom — and moving the stop
moves the SPX-mark trigger with it, by the same delta walk in reverse.

**One close in flight per position, and the bracket comes off before the close
goes on.** The SPX-mark loop and the broker-resident stop are designed to fire
at the same price, so the service never lets both a close and a resting leg
rest at the broker at once: `_market_close` cancels the stop and then the
target first, and every failure branch afterwards puts both back — a cancel
that finds a leg already filled books that fill and sends nothing, a broker
that cannot be reached leaves what still rests standing as the protection it is
(a stop that had already come off goes back on), a rejected close re-rests
both. A close that comes back WORKING is remembered on the position
(`exit_order_id`), in the journal (`exit_unfilled`), and across a restart, and
while it is in flight the loop reports it as pending instead of firing again —
re-sending the close every tick until one filled was finding 2 of the
2026-08-30 audit, an oversell that grew once a second. `flatten` is the one
caller allowed to jump the queue: it cancels an in-flight close and replaces it,
because "get me out" must not wait behind an earlier, slower exit. One residual
is recorded on `st-97z1`: a *partial* manual exit leaves the full-size bracket
standing while it rests.

**The day is derived from the journal, not remembered.** Open positions, the
realized-loss ceiling and the attempts used are rebuilt by reading the file
(`execd/journal.py`), so a restart recovers them. Losses only debit the ceiling;
a winner does not raise it. Attempts follow Steve's 2026-09-14 rule (st-fn5y):
*"an 'attempt' is a 'filled position'. Any attempt that breaks even or better
doesn't decrement the counter"* — so an attempt is held by a filled position
while it is open and kept only if it closes at a loss, judged on the whole
position's P&L once nothing is left; a working entry holds a position slot (it
closes the entry door) but no attempt. On this box, restarts are not
hypothetical.

**The ceiling bounds the position in front of it, not only the day behind it.**
Every ceiling check used to look backwards at loss already realized, so two
attempts could each realize more than the whole day's ceiling with every bound
passing. `check_risk_budget` prices an entry at its limit — the most a buy can
pay, so the most it can lose — walks it down to the stop it would rest, and
refuses if that exceeds the headroom left. The same arithmetic, run before the
send rather than after the fill, is why a contract too cheap to leave room for a
stop is now refused instead of becoming a live unprotected position. Steve
raised the ceiling from $100 to $500 on 2026-08-31 to make the bound bindable:
below the price of one position it is a number, not a bound.

**What is open is read from the broker, not believed.** The journal is the
authority on what this service *intended*; only the broker knows what is *held*,
and `ExecService.reconcile` asks it — at start-up, before every entry, before an
exit is sized, and before a flatten. An entry the broker acknowledges without
filling is a `working` entry: it holds a position slot (not an attempt — an
attempt is a filled position, Steve 2026-09-14) until reconcile learns what
became of it, so an order resting at the broker can no longer be repeated
without limit. Filled ones become tracked positions and get the bracket they
were owed; cancelled and rejected ones give the slot back; ones the broker cannot account for keep it, because holding a slot only
refuses new risk while forgetting one creates it. A position found at the broker
that **this service tried to open** — any contract in the last week of journals
with a `sending`, `working` or `filled` line — and lost track of is adopted so
`flatten` can close it. Anything else the account holds on this service's
instruments is **Steve's**: shown on the page and on `/status` as
`foreign_positions`, journaled once as `position_foreign`, never slotted and
never flattened. (Until 2026-09-15 every long leg was adopted; the audit's
finding 30 wrote out the morning he holds a butterfly by hand, unlocks, and
FLATTEN sells the wings — st-isx3.) A tracked size that disagrees with the
broker's is corrected to the broker's. A position must be absent from the
broker's account for `POSITION_SETTLE_S` before it is believed closed — a
positions endpoint lagging a fill it just reported is ordinary, and treating
that as a close would cancel the stop under a live trade.

**A send is journaled before it goes out.** `sending` carries the intent's
shape; if the broker's answer never comes back (`send_unknown`) the intent is
held as unconfirmed — every entry is refused `send_unconfirmed`, the same
intent most of all — until reconcile's **orphan sweep** has matched it to the
broker's listing by contract, side, size, limit and time (`send_resolved
found`, and it becomes the working entry or the position) or found nothing
after `SEND_SETTLE_S` (`send_resolved not-found`; the intent may be re-sent).
The sweep also identifies an `unnamed:` working entry from the listing and
journals any other working buy on these instruments once as `foreign_order`,
shown, never adopted (finding 25, st-xlz9).

**A cancel is an ask.** The transport re-reads after its DELETE until the
status is terminal or `CANCEL_CONFIRM_S`; a leg still `WORKING` at the deadline
is **not off** — `cancel_pending` is journaled, a close in progress is
DEFERRED with the bracket still resting, and a leg an already-booked close
could not confirm is carried as a **loose leg** (`leg_unconfirmed`, on
`/status`, rebuilt on restart) that every reconcile asks after until it is
`leg_resolved` — or, if it filled after the position closed, booked
`oversold`. What the broker holds short is journaled `short_held` and shown;
a `SELL_TO_CLOSE` fill on a symbol not held is journaled `unattributed_sell`
once; a sell on a held symbol from an order this service did not place is
booked as an `external` close (finding 24, 29, 39; st-7ah8).

**STOP takes no lock.** `service.stop()` touches the kill file before anything
else and never takes the service lock, so a STOP from the page during a slow
entry refuses the send instead of queueing behind it (finding 35, st-jm6u).

This is the fix for finding 1 of the 2026-08-30 independent audit
(`st-v7oa`): the service transmitted on what was *requested* and counted on what
*filled*, and those are the same event only against a mock that fills
synchronously. `tests/execd/test_reconcile.py` is what it has to mean.

## The journal

Append-only JSONL, one file per Central trading day under
`<state-dir>/journal/`, every line stamped with the git sha of the copy that
wrote it and fsync'd before the call returns. `request`, `refused` with its
bound, `preview`, `placed`, `working`, `entry_resolved`, `filled`,
`stop_placed`, `stop_unprotected`, `target_placed`, `target_unprotected`,
`stop_adjusted`, `target_adjusted`, `oversold`, `exit_triggered`, `exit_unfilled`,
`exit_resolved`, `closed` with its P&L, `canceled`, `position_adopted`,
`position_foreign`, `position_corrected`, `position_gone`, `reconcile_unknown`,
`exit_unverified`, `sending`, `send_unknown`, `send_resolved`,
`working_identified`, `foreign_order`, `cancel_pending`, `leg_unconfirmed`,
`leg_resolved`, `short_held`, `short_covered`, `unattributed_sell`,
`unlock`, `stand_down`, `stop`, `recovered`.
It is the audit "trust the process" rests on, and on the first live day it is
read back against Schwab's own order history before there is a second.

## The Schwab transport

`execd/schwab.py`. `SchwabBroker` is the second `Broker`; the service never
learns which one it holds. What it does that the mock does not:

- **Asks for the credential on every call** through the arming state
  (`bind(service.arming)`), so a lock is a lock on the transport with no second
  flag to forget. The vault payload is `{"app": {"key", "secret"}, "token":
  <schwab-py wrapped>}`. The access token it derives lives in memory only and
  is refreshed from the refresh token when it nears expiry; refreshing never
  touches the vault, because the refresh token does not change on refresh.
  Past the seven-day wall it refuses before making a call.
- **Sends GET, POST and DELETE, never PUT.** Schwab's replace-order verb is
  absent from the module and a test reads the source to keep it so, which is
  what keeps a bounded chase (st-kdaq) from arriving as a one-line change.
- **Retries nothing that sends.** A GET that meets a 401 refreshes once and
  retries once; a POST that meets one is reported, and the service's reconcile
  finds out what went in.
- **Reports positions by OCC root, never by the account body's
  `underlyingSymbol`.** A leg is this service's to see when
  `parse_occ(symbol).root` is in `roots` — the bounds' `instruments` in
  production, SPX and SPXW by default. The account body's `underlyingSymbol`
  has never been recorded for an option leg, while every recorded *order* leg
  for an SPXW contract says `SPXW`; the old filter on `SPX` would have
  excluded the service's own position and cancelled its bracket ninety
  seconds after the first live fill (finding 23, st-zm2u). A share position
  is not this service's to flatten, so it is not shown; what was left out is
  counted in `excluded_positions`, which `/status` and the page carry.
- **A cancel is re-read until it is terminal** (`CANCEL_CONFIRM_S`, twelve
  polls at `CANCEL_POLL_S`); a `PENDING_CANCEL` at the deadline comes back
  `WORKING` with the broker's word in `message` (st-7ah8).
- **Never puts a secret in a message.** No token, key or account identifier
  reaches a log or an exception; the account hash is `<account>` in every path
  it quotes.

A `place` is a 201 with the order id in the `Location` header, followed by a
read of the order; a 400 is returned as a rejection, not raised. A `cancel`
is a DELETE followed by the same read, so cancelling a stop that already
filled reports the fill — the race the exit path is written to survive.

`scripts/record_schwab_shapes.py` is the recorder: read-only, plain HTTPS,
scrubs account identifiers at capture, writes `tests/fixtures/schwab/` with a
`_capture.json` that says when and in what market state.

## What comes next

| stage | bead | what lands |
|---|---|---|
| 2 | st-w2nw | **built**; trader read shapes recorded 09-05. Open only for the live read-only proof, which is stage 3's first unlock. |
| 3 | st-p8k8 | **built 2026-09-13** — user, unit, `deploy/install.sh --execd`, the page, the readers re-pointed, the hook change presented. Pending Steve: the passphrase, the install, the hook, the first unlock; then the token files retire. |
| 4 | st-k6gl | a full rehearsal with sending disabled, then one 1-lot live single with Steve at the STOP button |
| 5 | st-47i2 | FD0 tickets and promoted rules become intents; the paste line retires |

Order is strict. Nothing sends before stage 4.
