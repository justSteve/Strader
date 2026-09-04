# execd — the live execution service

The one holder of the broker credential on this box. Steve ruled the wall
crossing on 2026-08-30 (st-l3s4): *code executes live trades against the API,
the token is hidden from agents, pasting is not the long-term transport.*
This is that service. Epic **st-5qjq**; design of record
`docs/a2a/2026-08-30-coo-to-strader-live-execution-service-plan.md`.

**Stages 1 and 2 are what is here.** Two brokers: `MockBroker` (stage 1,
st-eznu) and `SchwabBroker` (stage 2, st-w2nw) — the Trader API over plain
HTTPS in `execd/schwab.py`, the one module in the package that imports a
transport. There is still no credential on disk here (the vault holds it,
encrypted) and no import of the repo's hobbled `schwab` library —
`tests/execd/test_wall.py` asserts all of it by reading the source and by
watching what a full import actually loads.

**What stage 2 could and could not record.** The market-data shapes the
client reads were recorded against the live API on 2026-09-04
(`tests/fixtures/schwab/`). The Trader API shapes — account numbers,
positions, orders, preview — could not be: measured that morning, the app
registered for this box answered every `/trader` path with HTTP 401
`no apiproduct match found`, which is Schwab saying the **Accounts and
Trading product is not on the app**. That is Steve's developer-portal change.
Until it lands and `scripts/record_schwab_shapes.py` is re-run, those parts
of the client are written to the API specification and say so in their
docstrings; the tests mark their fixtures `SPEC`.

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

Fourteen routes on the loopback, JSON in and out. `200` the service acted,
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
| `POST /stand-down` · `POST /stop` | done for the day; the kill switch on |
| `POST /observe` · `POST /poll-fills` | feed it the SPX mark; pick up a stop that fired |

**What is deliberately absent: `/unlock`, `/resume`, and any re-auth route.**
An agent that can reach this API can ask the service to trade inside Steve's
bounds. It cannot arm it, cannot clear his STOP, and never sees the credential.
That claim is asserted against the app's own URL map, so adding a route back
breaks the suite.

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
| `ceiling` | $500 realized loss, 2 attempts — rebuilt from the journal, so a restart does not reset it; and the entry's own worst case, limit down to its derived stop, must fit the headroom left |
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
quietly.** The stop's inputs are checked before the entry is previewed. On the
fill the service derives the option-price stop from the SPX level through delta
(`execd/stops.py`) and rests it at the broker, so a dead box still has a stop;
while the box is alive `observe(spx)` runs the accurate SPX-mark exit and
cancels the resting order when it fires. A broker that refuses the resting stop
is journaled as `stop_unprotected` — loud, because the position is live. When
an exit fills only partly, the resting stop — sized for the whole position — is
cancelled and re-rested at the smaller size, because a stop larger than the
position would sell contracts Steve no longer owns.

**One close in flight per position, and the stop comes off before the close
goes on.** The SPX-mark loop and the broker-resident stop are designed to fire
at the same price, so the service never lets both a close and the stop rest at
the broker at once: `_market_close` cancels the stop first, and every failure
branch afterwards puts it back — a cancel that finds the stop already filled
books that fill and sends nothing, a broker that cannot be reached leaves the
stop standing as the protection it is, a rejected close re-rests it. A close
that comes back WORKING is remembered on the position (`exit_order_id`), in the
journal (`exit_unfilled`), and across a restart, and while it is in flight the
loop reports it as pending instead of firing again — re-sending the close every
tick until one filled was finding 2 of the 2026-08-30 audit, an oversell that
grew once a second. `flatten` is the one caller allowed to jump the queue: it
cancels an in-flight close and replaces it, because "get me out" must not wait
behind an earlier, slower exit. One residual is recorded on `st-97z1`: a
*partial* manual exit leaves the full-size stop standing while it rests.

**The day is derived from the journal, not remembered.** Open positions, the
realized-loss ceiling and the attempts used are rebuilt by reading the file
(`execd/journal.py`), so a restart recovers them. Losses only debit; a winner
does not buy back an attempt. On this box, restarts are not hypothetical.

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
filling is a `working` entry: it holds a position slot and an attempt until
reconcile learns what became of it, so an order resting at the broker can no
longer be repeated without limit. Filled ones become tracked positions and get
the protective stop they were owed; cancelled and rejected ones give the slot
back; ones the broker cannot account for keep it, because holding a slot only
refuses new risk while forgetting one creates it. Positions found at the broker
that this service never opened are adopted so `flatten` can close them, and a
tracked size that disagrees with the broker's is corrected to the broker's. A
position must be absent from the broker's account for `POSITION_SETTLE_S` before
it is believed closed — a positions endpoint lagging a fill it just reported is
ordinary, and treating that as a close would cancel the stop under a live trade.

This is the fix for finding 1 of the 2026-08-30 independent audit
(`st-v7oa`): the service transmitted on what was *requested* and counted on what
*filled*, and those are the same event only against a mock that fills
synchronously. `tests/execd/test_reconcile.py` is what it has to mean.

## The journal

Append-only JSONL, one file per Central trading day under
`<state-dir>/journal/`, every line stamped with the git sha of the copy that
wrote it and fsync'd before the call returns. `request`, `refused` with its
bound, `preview`, `placed`, `working`, `entry_resolved`, `filled`,
`stop_placed`, `stop_unprotected`, `exit_triggered`, `exit_unfilled`,
`exit_resolved`, `closed` with its P&L, `canceled`, `position_adopted`,
`position_corrected`, `position_gone`, `reconcile_unknown`, `exit_unverified`,
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
- **Reports positions in the index's options only.** The service adopts every
  position it is shown so `flatten` reaches it; a share position in the same
  account is not this service's to flatten, so it is not shown. What was left
  out is counted in `excluded_positions` for the status page.
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
| 2 | st-w2nw | **built** — the transport, the vault, the OAuth helpers for the page. Open on it: the Trader API shapes are spec-derived until the Accounts and Trading product is on the app and the recorder is re-run. |
| 3 | st-p8k8 | dedicated user, systemd unit, `deploy/install.sh`, the tailnet page that takes the passphrase and runs the weekly re-auth, the plaintext token retired |
| 4 | st-k6gl | a full rehearsal with sending disabled, then one 1-lot live single with Steve at the STOP button |
| 5 | st-47i2 | FD0 tickets and promoted rules become intents; the paste line retires |

Order is strict. Nothing sends before stage 4.
