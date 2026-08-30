# Execution engine — the road from v0.7 to v1 of its CLI

**Steve, 2026-08-30:** *"a roadmap of v1 of the system's CLI — whatever currently
exists can be thought of as V.07."*

Companion to `docs/execution-engine-operations-manual.md`, which describes v0.7
exactly as it stands. This document says what v1 is, what stands between here
and there, and in what order. Nothing on it crosses the wall: **the CLI cannot
send before execd stage 4**, and it never becomes a second place where bounds
live.

---

## 1. What v0.7 actually is

Not "a CLI with gaps". Three unrelated command surfaces that happen to share a
repository:

| Surface | Shape | Ends at |
|---|---|---|
| `python -m strader.intent` | an interactive dialect — 15 verbs, free dictation, a day plan on disk | a paste line in Steve's clipboard |
| `python -m execd --mock` | a server launcher with six flags | a loopback API with **no client** |
| four loose scripts | `feed --preflight`, `fire_server.py`, `refresh_schwab_token.py`, `schwab_token_health.py` | stdout |

Four observations that set the work:

1. **There is no `strader` command.** `pyproject.toml` has no
   `[project.scripts]`. Every invocation is a path into a virtualenv plus a
   module or script name. Nothing is discoverable; nothing has a shared `--help`.
2. **execd's fourteen routes have no caller.** The operator surface today is
   `curl` against `127.0.0.1:8778`. That is fine for a test and wrong for a
   person, and it is the single largest gap between what the service can do and
   what anyone can ask it to do.
3. **The two halves do not meet.** The intent desk produces a *paste string*;
   execd consumes an *OrderIntent JSON*. Joining them is execd stage 5
   (`st-47i2`) and is the substance of v1.
4. **The edges are inconsistent in ways that cost a re-read.**
   `feed --token` defaults to a path that does not exist;
   `refresh_schwab_token.py` has no `--help` at all; `execd --host` is hidden
   from help but exits 2 if you use it; nothing anywhere emits `--json`.

## 2. What v1 is

**One command that covers the operator's whole day, with the dialect preserved
inside it and the bounds still living in the service.**

```
strader intent                     # the dialect REPL — unchanged behaviour
strader intent --once "…"
strader exec serve --mock          # what `python -m execd` is today
strader exec status                # the fourteen routes, as verbs
strader exec quote SPXW…           strader exec chain SPX
strader exec preview FILE|-        strader exec place FILE|-
strader exec orders                strader exec positions
strader exec journal [-n N]        strader exec observe 6320.5
strader exec cancel ORDER_ID       strader exec flatten [--reason R]
strader exec stand-down            strader exec stop
strader exec poll-fills
strader token status               strader token refresh
strader preflight
strader fire serve
```

Three properties make it v1 rather than a tidier v0.7:

**a. The client is thin, and provably so.** `strader exec place` builds an
`OrderIntent`, posts it, and prints what came back. It performs **no check of
its own**. Every bound stays in `execd/bounds.py`, where the caller is not
trusted — the engine, the intent desk, an agent with a curl command and the page
all reach the same door. A CLI that started validating quantities would be a
second place a rule could be missed, and stage 5 adds a second caller to this
same service. This is worth a test that asserts the client module imports
nothing from `execd.bounds`.

**b. A refusal reads as a refusal.** `409` with `{"bound", "reason"}` becomes a
non-zero exit and one line naming the bound. Exit codes: `0` acted, `3` a bound
refused it, `4` the broker could not be reached, `2` the request was malformed.
A person and a script get the same answer.

**c. `go` stops ending at the clipboard.** In v1 the intent desk's `go` writes
its staged ticket *and* an execd intent, and `strader exec place` can take it.
The paste line stays — as the fallback, not the transport.

### What v1 is deliberately not

- **Not a TUI.** Steve learns by watching parts move, and the surface for that
  is the tailnet page (execd stage 3), reachable from his phone. The CLI is the
  surface for COO, for scripts, and for his keyboard.
- **Not a new dialect.** The fifteen verbs stay exactly as they are. The dialect
  is the one part of v0.7 that is already at v1.
- **Not a rules engine.** Promotion of rules to intents is execd stage 5's
  business, not the CLI's.
- **Not a second home for the bounds.** See (a).

## 3. The design constraint that decides the arguments

Steve's own standard, from the reader profile: *builder and operator are
different people; build tooling an intelligent operator who did not build it can
run, read and repair.* He ran a production estate for years and his vocabulary is
API, SQL, DNS, IIS, cron. What costs him is shorthand and post-2016 idiom.

So: long flags, whole words, no single-letter options except `-n` and `-v`;
every command prints what it did in a sentence before it prints data; `--json`
for the machine path and human text by default; and no command that needs a
second command to explain it.

## 4. The ladder

Three releases. Each is shippable on its own and leaves the engine working.

---

### v0.8 — a client for execd

*Nobody should ever type `curl` at a service that can trade.*

| | |
|---|---|
| **Adds** | `execd/client.py` (a thin HTTP client) and `strader exec …` covering all fourteen routes |
| **Changes nothing** | in `execd/service.py`, `bounds.py`, `api.py` |
| **Blocked by** | nothing |
| **Bead** | to file — child of `st-5qjq`, sibling of the stage work |

Acceptance:

- Every route in `execd/api.py` has a subcommand, and a test asserts that
  correspondence by reading the app's URL map — so a route added later without a
  subcommand fails the suite, the same way `test_api.py` already guards the
  absent `/unlock`.
- The client imports nothing from `execd.bounds` (asserted).
- `--json` on every read command.
- Exit codes as in §2b, tested against a live app fixture.
- `strader exec place` refuses to run against a non-loopback host, the same way
  the server refuses to bind one.

The one design question this release settles: **`place` takes a file or stdin,
never a pile of flags.** An intent is eleven fields with cross-field rules; a
command line that could express it wrongly is a command line that will. `-` reads
stdin, so `strader exec preview ticket.json` and
`… | strader exec place -` both work.

---

### v0.9 — one front door

*Everything the operator runs, under one name, with one `--help`.*

| | |
|---|---|
| **Adds** | `[project.scripts] strader = "strader.cli:main"`; the `strader` command; subcommand dispatch |
| **Absorbs** | the four loose scripts, as `token status`, `token refresh`, `preflight`, `fire serve` |
| **Blocked by** | nothing |
| **Bead** | to file |

Acceptance:

- `pip install -e .` puts `strader` on the path; the venv path prefix stops
  being part of every instruction in every document.
- Every v0.7 entry point still works unchanged. **Nothing is removed in this
  release** — the old `python -m` forms keep working, so no runbook, cron entry
  or muscle memory breaks on the day it lands. Deprecation is a v1.0 decision,
  and probably a "never".
- `strader --help` lists the day: intent, exec, token, preflight, fire.
- The three inconsistencies from §1.4 are fixed in the same release:
  `preflight --token` gets a correct default, `token refresh` gets a real
  `--help` that says the login is Steve's, and `exec serve --host` becomes a
  documented flag that still refuses anything but the loopback.

Full mapping, so nothing is lost:

| v0.7 | v0.9 |
|---|---|
| `python -m strader.intent …` | `strader intent …` |
| `python -m execd --mock …` | `strader exec serve --mock …` |
| `python -m strader.execution.feed --preflight --token P` | `strader preflight` |
| `python scripts/schwab_token_health.py --no-bead --no-push` | `strader token status` |
| `python scripts/refresh_schwab_token.py` | `strader token refresh` |
| `python scripts/fire_server.py --port N` | `strader fire serve --port N` |
| *(curl against 127.0.0.1:8778)* | `strader exec <verb>` |

---

### v1.0 — the join

*The dialect's `go` and the service's `place` become the same act.*

| | |
|---|---|
| **Adds** | an `OrderIntent` emitter on the intent desk's `go`; `strader exec place` accepting it directly |
| **Blocked by** | execd **stage 2** (`st-w2nw`, the Schwab transport) and **stage 4** (`st-k6gl`, the first live 1-lot). This release does not send; it makes sending possible without a paste. |
| **Bead** | execd stage 5, `st-47i2` |

Acceptance:

- `go` writes `data/intent/staged/<stamp>-<shape>.json` **and**
  `<stamp>-<shape>.intent.json` — the second in execd's wire form, with
  `intent_id` derived from the stamp so it is idempotent by construction, and
  with `stop_spx` and `delta` carried across from the FD0 bracket, because an
  entry without them is refused by bound 6.
- The paste line is still printed. It remains the fallback and the thing Steve
  can always fall back to, and there is no release in which it is removed.
- One journal read spans both halves: `strader exec journal` and the day plan's
  own log can be shown against each other for a single trading day.
- A butterfly emits **no** intent — execd is SPX/SPXW long-premium singles at
  stage 1–4, and a fly has no protective stop to derive. It emits the paste line
  only, and says so.

**The order is strict.** v1.0 lands the plumbing; whether an intent is ever
*sent* is governed by execd's stage ladder and by Steve, not by this roadmap.

---

## 5. What this roadmap deliberately leaves alone

- **The wall.** All four layers stay exactly as they are. execd's narrow
  exception stays narrow, and `FORBIDDEN_TRANSPORTS` still gets edited by hand,
  visibly, in the commit that adds a transport.
- **The intent dialect.** Fifteen verbs, unchanged.
- **The bounds.** Twelve of them, service-side, non-negotiable in shape.
- **The fire server.** It keeps its own page and its own rails until execd
  stage 3's page supersedes it. Retiring it is a separate decision with its own
  review, per the live-monitoring registry.

## 6. Sizing

| Release | Rough shape |
|---|---|
| v0.8 | one new module plus a subcommand file; the tests are the interesting half |
| v0.9 | mostly wiring and a `[project.scripts]` line; the risk is breaking a cron entry, which is why nothing is removed |
| v1.0 | small in code, gated by stage 2 and stage 4 |

None of the three is large. The reason v0.7 is not already v1 is not difficulty;
it is that each piece was built when it was needed and nothing has yet been
asked to be one thing.

## 7. The open question, and a recommendation

**Command name.** `strader` is the obvious choice and matches the package. It is
also eight characters typed many times a day. `sx` as an alias is one line in
`[project.scripts]` and costs nothing.

Recommendation: ship `strader` as the name and `sx` as an alias in the same
release. No decision needed unless Steve wants a different word.
