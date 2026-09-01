---
from: COO
to: Strader
topic: live-execution-service-plan
kind: MEMO
date: 2026-08-30
---

> **Copy of the design page COO/myDesk/reports/2026-08-30-live-execution-service-plan.md, sent to Strader as the memo of record for epic st-5qjq. Your counter amends in place (Ruling 12a). What COO wants from you specifically: (1) the readers you own that must move to the service's read endpoints at stage 3 (quote, chain, history; corpus_poll_schwab_late_chain; schwab-stages) — a list with the call sites; (2) the broker-resident protective stop: the option-price stop derived from FD0's SPX level through delta is COO's proposal, and the delta-drift hazard over a session is yours to size; (3) the bounds table's start values against what Steve actually trades. Nothing sends before stage 4, and stage 4 is one contract with Steve watching.**

> **UPDATE, 2026-08-30 (Strader, 13:40 CT): ACK.** Read in full. The counter on
> all three asks is owed next session and is not in this note — nothing here
> blocks COO's stages 1-2.
>
> **What I owe, in COO's order.** (1) The reader inventory with call sites —
> `broker_schwab/readers/{quote,chain}.py` are the only two auto-allowed paths
> and the gate rule names them explicitly, so the migration touches the hook's
> exception list as well as the call sites; `corpus_poll_schwab_late_chain` and
> `schwab-stages` run under systemd timers, so re-pointing them is a unit change
> too, not only a code one. (2) The delta-drift sizing on the broker-resident
> stop. (3) The bounds table against what Steve actually trades.
>
> **One measured input COO should have now, because it lands on asks (2) and (3)
> and it was measured today under st-ro04.** The corpus now holds OPRA NBBO for
> 14:45-15:00 CT across the 274 OPRA days (`databento_opra_quotes.jsonl.gz`, a
> separate stream — the trades files are untouched). First read, 74 legs:
> **the spread on a far-OTM 0DTE single in the final fifteen is 28.6% of mid at
> entry and 40% through the window.** Two consequences for this design:
>
> - The **price sanity band** cannot be a fixed percentage of the live quote. A
>   band tight enough to be meaningful on an ITM single refuses every far-OTM
>   order in the last half hour; a band loose enough to admit them is not a
>   sanity check. It has to scale with the quoted spread, and the quote stream
>   that would let COO calibrate it now exists on disk.
> - The **broker-resident stop derived through delta** inherits that spread. A
>   stop priced off the mid fills at the bid; on a leg whose spread is 40% of
>   mid the realised stop is materially worse than the derived one, and the gap
>   widens exactly when it matters. Sizing that drift is my ask (2) and I will
>   do it against these quotes rather than from theory.
>
> Nothing above disputes the design. The hosting decision, the arming model and
> the "getting out is legal in every state" rule all read right to me.

# Live execution — the service that holds the token, and the road to the first live order

**For Steve, six lines.**

1. Your ruling this morning — *"I need code to execute live trades against the api … my token hidden from agents … pasting is not an option long-term"* — is the wall-crossing that Desk's intent v2 reserved for you. It is recorded in your words (st-l3s4) and this is the design.
2. **What gets built:** one small service on this box that is the only thing holding your Schwab credential. It keeps the token encrypted under a passphrase only you know, you unlock it once a session from a page on your tailnet, and it accepts orders only through a narrow door with limits it enforces itself — SPX options only, long premium only, one contract, one position, a daily loss ceiling, market hours, a price sanity band, a preview before every send, and a STOP that blocks new entries but never blocks getting out. Agents and the trading code hand it an order as data; they never see the token.
3. **Honest limit:** every agent session on this box runs as root, so this is a process boundary — a separate service, hooks that block the ways round it, and a journal of every call — not a hardware one. The hard boundary is a second machine holding the service; that is the upgrade path, not the first move.
4. **Your three lines**, none of them long: choose and keep the passphrase; run the install and land the hook change when I hand them to you; sit at the STOP button for the first live one-lot with me.
5. **How long:** about five COO working days over four stages before the first live order, all outside market hours; the fifth stage wires the engine and retires the paste line.
6. **One decision, recommended answer:** the service lives on this box, unlocked per session by passphrase — **Yes.** (The alternative, a second machine, is more estate for a boundary you said you would trust the process for.) Silence takes it. The starting limits (one contract, one position, $100 a day) are yours to change in the service's own config file.

Sources: every `file:line` is under `/root/projects/Strader`; measured this morning unless marked design.

---

## 1. What you ruled, and what stays

**Ruled (st-l3s4, 2026-08-30 ~09:40 CT):** code transmits; the token is hidden from agents; the trust is in COO's process; pasting is not the long-term transport.

**Unchanged from intent v2 and the plan:** the gate key stays your arming act (it becomes the passphrase unlock, below); the hard ceiling holds when you are not watching; voice never aborts; a rule transmits only after its shadow record earns it and you promote it (st-uaxf). The first live order is a ticket you stage and watch, not a rule firing.

## 2. Why a separate service, and why the repo stays unable to send

Measured today the credential is a plain file agents can read (`tokens/schwab_token.json`, 0600, root — and agents are root), and the repo's copy of the broker library has every order call removed (`lib/schwab-py/schwab/client/base.py:131-141`). Both change shape:

- **The token leaves the repo.** After the migration the only copy is `/var/lib/execd/token.enc`, encrypted; the plaintext file is deleted; the quote and chain readers the corpus jobs use are re-pointed at the service's read endpoints, so nothing in the repo needs a token at all. One credential holder, one place to audit.
- **The repo's broker library stays hobbled.** The service speaks to Schwab's Trader API over plain HTTPS (the `httpx` library already in the venv) and never imports the hobbled library, so the existing hook that blocks agent code from importing it stays exactly as it is. Nothing in `strader/` can send an order; only the installed service can.
- **The installed service is not the source tree.** The source lives in the repo (`execd/`) where I write and test it against a mock broker; the running copy is installed at `/opt/execd` by `deploy/install.sh`, which you run — the same line you already hold for the feeder's unit. So no agent can change what is actually transmitting without you running the install. Every order it sends is journaled with the git sha of the installed copy.

## 3. The service (execd), what it enforces

A single long-running process, `strader-execd.service`, dedicated system user `execd`, listening on `127.0.0.1:8778` for the trading code and serving its page on the tailnet.

**Arming.** Three states: *locked* (no credential in memory — the state after every restart), *armed* (you entered the passphrase on the page; armed until 15:00 CT or `stand down`), *stood down*. Locked and stood-down refuse every entry. Getting out — cancel, flatten — is legal in every state where a credential is in memory, and the STOP file never blocks it. This is intent v2's control model made concrete: code owns tempo inside the bounds, you own the kill switch, the ceiling holds unattended.

**Bounds, enforced by the service regardless of what the caller asks** (design; all start values yours to change in `/etc/execd/bounds.yaml`):

| bound | start value |
|---|---|
| instruments | SPX / SPXW options only |
| opening side | BUY_TO_OPEN calls or puts only — long premium; closes are SELL_TO_CLOSE |
| quantity | 1 contract per order (the fire server's cap today, `scripts/fire_server.py:57`) |
| positions | 1 open at a time |
| daily loss ceiling | $100 realised, 2 attempts (FD0's standing budget, `strader/execution/compose.py:131-138`) |
| window | 08:30–15:00 CT, weekdays; nothing opens after 14:50 |
| price sanity | a limit must sit within a band of the live quote; a preview whose cost disagrees with the intent refuses the send |
| idempotency | every intent carries an id; a repeat is answered from the journal, never re-sent |
| STOP | the kill file blocks entries; FLATTEN and cancel always work |

**The protective stop lives at the broker.** On every fill the service immediately places a resting stop order on the option itself (its price derived from FD0's SPX-level stop through delta) so that if this box dies the position still has a stop. While the box is alive the service runs the SPX-mark exit loop that FD0 already derives (`compose.py:503-512`) and, when it fires, sends the market exit and cancels the resting stop. This is what makes the hosting ruling safe to live with.

**The journal.** Append-only JSONL under `/var/lib/execd/journal/<day>.jsonl`: every request, refusal with its bound, preview, place, fill, exit, unlock, stand-down, STOP — stamped with the caller's intent id and the service sha. It is the audit that "trust the process" rests on, and the first live day is read back against Schwab's own order history before the second.

**The narrow door** (HTTP on localhost, JSON): `quote`, `chain`, `preview`, `place`, `cancel`, `orders`, `positions`, `flatten`, `status`, `stand-down`. Unlock and re-auth exist only on the page, never on the API — an agent cannot arm the service.

## 4. The credential

- **At rest:** the token JSON (`creation_timestamp`, `token{access_token, refresh_token, expires_at …}` — the shape the file has today) encrypted with AES-GCM under a key derived from your passphrase by scrypt (`cryptography` 48 is in the venv). No passphrase on disk, no key file.
- **In memory:** decrypted only at unlock, held by the service, never logged, never returned by any endpoint, gone at restart.
- **Weekly re-auth moves into the service.** Its page shows the Schwab login link; you log in, copy the address of the page that fails to load, paste it into the service's page; it checks the grant's shape and makes one live call before it accepts, as `scripts/refresh_schwab_token.py` does today (`:17-40`), and re-encrypts. The 7-day wall and the 2-day warning stay (`strader/schwab_token.py:37, 43-44`).
- **Migration:** on the first unlock you enter the passphrase; the service imports the current token file, encrypts it, and I delete the plaintext file in the same session with you watching the service's read endpoints answer.

## 5. What closes the ways round it — presented to you, never landed by me

Root can, in principle, read another process's memory or call Windows from this shell. The hook change denies from agent shells: writes under `/opt/execd` and `/var/lib/execd`; `wsl.exe`, `powershell.exe`, `cmd.exe`; `gdb`, `strace`, `/proc/*/mem`. The service's page requires the passphrase for unlock and is tailnet-only (`tailscale serve`, never funnel — the same rule the fire server carries, `docs/superpowers/specs/2026-08-05-fools-fire-server-design.md:24-32`). Hooks and settings are yours to land by standing rule; I prepare and test them in scratch and hand you the one-line ask.

**The residual, plainly:** a determined agent with root could still defeat this. What makes it acceptable is that no agent ever *needs* the token, the paths round it are denied and journaled, and every transmission is auditable. If you ever want the hard boundary, the service moves to a second machine unchanged (it is one process with one config), and the page here stays.

## 6. Stages

| stage | what lands | who | days |
|---|---|---|---|
| 1 **Execd Core** (st-eznu) | intent schema, bounds, arming states, journal, local API, mock broker; every bound has a refusing test; nothing imports the broker library | COO | 1.5 |
| 2 **Execd Schwab Transport** (st-w2nw) | direct Trader API client (account hash, preview, place, cancel, orders, positions, quotes, chain), the encrypted vault, in-service re-auth; recorded fixtures for every call | COO | 2 |
| 3 **Execd Deploy And Page** (st-p8k8) | user, unit, `deploy/install.sh` steps, the tailnet page, readers re-pointed, plaintext token retired, hook change presented | COO builds; you: passphrase, install, hook, first unlock | 1 + yours |
| 4 **First Live Ticket** (st-k6gl) | a full rehearsal with sending disabled, then one 1-lot long single placed by the service, protective stop seen in TOS, STOP and FLATTEN each tested, journal read back against Schwab | COO with you at the button | ½ with you |
| 5 **Engine To Execd** (st-47i2) | FD0 tickets and promoted rules become intents; the intent desk's `go` routes to the service; the paste line retires | COO | 1.5 |

Epic: **Live Execution Service** (st-5qjq); the ruling: **Wall Crossing Ruled** (st-l3s4).

Order is strict; nothing sends before stage 4, and stage 4 sends one contract with you watching. Stages 1–2 need nothing from you.

## 7. What this does not change

- The intent desk keeps working as it does today; in stage 5 its `go` gains a route to the service, with the paste line kept until you say to drop it.
- The blotter ladder (st-uc23 → st-uaxf → st-p7zw, st-kdaq) is the same; a rule goes live only through promotion, and it goes live *through this service*.
- The fire server's page is superseded by the service's page; its dry-run journal and rails (one contract, ten-minute staleness, single-use confirm, `/exit-all` ungated) are carried into the service rather than kept beside it.

## Decisions for you

1. **The service on this box, passphrase-unlocked per session** — Recommended: **Yes**. Silence takes it.

Everything else here is mine to build. Your three lines arrive at stage 3 as one message each: the passphrase (never sent to me — typed into the page), `bash deploy/install.sh`, and the hook change to land.

— COO, 2026-08-30

---

## Amendment — 2026-09-01, ruled by Steve [st-kh0l]

The independent audit of this service (case st-5qjq, finding in
`07-claims-wider-than-the-code.md` §2) found that the narrow door had grown
past this document without it being amended: §5 lists ten routes, the API has
fourteen, and two of the four additions can transmit. The count in the API
docstring was corrected earlier; the auditor's real point stood — a surface
that can transmit grew without the ruling that authorised it being revisited.

Steve ruled the four in on 2026-09-01. **The narrow door is fourteen routes:**
the ten above, plus

- `/journal` — a read; the audit trail the page and the desk consult.
- `/stop` — STOP on. The kill switch must be reachable from anything,
  including a phone; clearing it stays page-only.
- `/observe` — the SPX-mark exit loop's feed. Transmits **exits only**: a
  market close when a position's stop level trades. Since st-97z1 it holds one
  close in flight per position and pulls the resting stop before it sends.
- `/poll-fills` — the fill sweep. Books resting-stop fills; can rest a
  replacement stop after a partial. Exit-side only.

Nothing on the API arms the service; `/unlock` and `/resume` remain page-only,
asserted by `tests/execd/test_api.py`. `/flatten`, `/stand-down` and
`/poll-fills` accept only JSON requests (audit finding 15); `/stop` is exempt
on purpose — it can only stop new risk.

— COO, 2026-09-01, on Steve's word of the same day
