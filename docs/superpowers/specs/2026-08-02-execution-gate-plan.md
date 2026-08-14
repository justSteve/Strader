# Execution Gate — Strader Authors, Steve Alone Executes

> **STATUS 2026-08-14 — OPEN, partially overtaken.** Tracked by st-5ey, moved out of `in_progress` back to `open` in this review (12 days untouched). Note the premise has shifted underneath it: the Schwab hard gate now exists in two enforced layers (the hobbled `lib/schwab-py` fork and the `schwab-gate.sh` PreToolUse hook), so "Strader authors, Steve executes" is already mechanically true for Schwab. Re-scope against `.claude/rules/schwab-api-gate.md` before building anything here.


**Bead:** Steve Holds The Key (st-5ey) · depends on Coded Counter Wisdom (st-ug5)
**Date:** 2026-08-02 · **Status:** plan for Steve's review

## The boundary, stated once

> **Strader may write, test, and stage any order-placement code. An order can
> only become an API call through a program that demands a secret and a
> keyboard — and only Steve has either.**

The current protection is *amputation*: the vendored schwab-py fork
(`lib/schwab-py`, branch `hobbled-readonly`) physically removes every
order/account/transaction method, so not even well-intentioned code can call
them. That protects against unintended execution but also forbids *authoring* —
Strader cannot build the execution harness (st-ug5 phase 2) against methods
that don't exist.

The new boundary moves the wall from *"the code cannot exist"* to *"the code
is inert without Steve."* This is a stronger kind of wall: it holds even if
every behavioral rule fails, because it is arithmetic, not policy.

## Why policy alone is not enough — said plainly

Today's stack (deny rules, the PreToolUse hook, the gate key file) is
*behavioral*: it tells the agent no. A behavioral wall is only as strong as
the session honoring it. The plan keeps every behavioral layer, but the
load-bearing wall becomes *cryptographic*: the trade-capable credential is
encrypted with a passphrase that exists only in Steve's head. The agent can
read every file on the distro and still cannot transact — decrypting the
credential without the passphrase is not "against the rules," it is not
possible.

One honest corollary about the *read* path: Schwab issues one token per app —
the token the readers use today is, at Schwab's end, already trade-capable.
What has protected it is the client-side amputation plus the deny rules. That
stays exactly as is; this plan neither weakens nor fixes it. The *new*
capability (an execution client that can actually send) appears only inside
the encrypted envelope.

## The three layers

### Layer 1 — Authoring surface (agent-permitted, fully open)

New package `strader/execution/` — importable, unit-testable, agent-written:

- **Order model** — entry/stop/target as SPX-structure terms (stop as SPX
  distance, option price derived via live delta — the st-5fm lesson), sized
  from `config/risk.yaml`.
- **Builders** — compose Schwab order payloads (OCO bracket, trigger-sequence,
  stop-limit) using the schwab-py *orders builder* modules, which survived the
  hobble untouched (`schwab/orders/common.py`, `options.py`). Builders are pure
  functions: payload in JSON out, no client, no network.
- **Preview renderer** — every payload renders to a human-readable ticket
  (symbol, side, qty, limit, stop trigger/limit, TOS-string equivalent) so a
  staged order is reviewable at a glance.
- **Staging** — `strader/execution/stage.py` writes the payload + ticket +
  SHA-256 hash to `data/exec/staged/<ts>-<slug>.json`. Staging is the agent's
  last touch. Nothing in Layer 1 imports an HTTP client.

Tests: builder round-trips against recorded chain fixtures; property tests on
the stop-derivation math; golden tickets. All runnable by the agent, no
credentials involved.

### Layer 2 — The execution gate (Steve-only)

One program: **`strader-exec`** (`runbook/exec_gate.py`, installed as a
console script). What it does, in order:

1. **Human-presence check** — refuses to run unless stdin is an interactive
   terminal. No pipe, no tmux send-keys, no subprocess capture.
2. **Unlock** — prompts for the passphrase; derives the key (scrypt) and
   decrypts `tokens/schwab_exec_token.enc` **in memory only**. Three failures
   or 60 s idle → exit. The plaintext token never touches disk, env, or argv.
3. **Load one staged order** — by filename; recomputes the SHA-256 and shows
   the ticket. A tampered or expired stage (>15 min old) is refused.
4. **Risk rails** — re-checks `risk.yaml` caps and `risk_state.py` HALTED
   *inside the gate*, so the rails hold even if the authoring layer lied.
5. **Confirm** — Steve types `SEND` (literal). Anything else aborts.
6. **Transmit** — via an *exec-capable* client (see dependency note below),
   then append the result to `data/exec/journal.jsonl` (append-only audit:
   ts, payload hash, order id, HTTP status).

The credential setup is a one-time ceremony Steve performs himself
(`strader-exec init`): it runs the OAuth flow, encrypts the token under his
passphrase, and shreds the plaintext. Rotation = re-run the ceremony (the
7-day refresh wall applies to this token too; the gate surfaces token age at
every unlock, reusing `strader/schwab_token.py`).

**Exec-capable client dependency.** Two options, decided at review:
(a) a `exec-capable` branch of our fork that reverts only the client-method
amputation — a small, reviewable diff against the DEFENSE NOTE
(`lib/schwab-py/schwab/client/base.py:132`); or (b) pin upstream schwab-py at
the fork point in a separate venv (`.venv-exec`) used only by the gate.
**Recommendation: (a)** — one codebase, one review, and the diff *is* the
DEFENSE NOTE's required ritual. The read path keeps importing the hobbled
branch; only `exec_gate.py` imports the exec-capable module path.

### Layer 3 — Enforcement against the agent (behavioral, kept and extended)

Three-layer alignment, per the COO convention:

| Layer | Change |
|---|---|
| Gate (`CLAUDE.md`) | New section: authoring permitted in `strader/execution/`; invoking `strader-exec`, reading `tokens/*exec*`, or touching `.venv-exec` is forbidden — with the actual paths named |
| Rule (`.claude/rules/`) | `no-autonomous-orders.md` rewritten around the author/execute boundary; `schwab-api-gate.md` gains the exec paths |
| Enforcement (`settings.json` + `schwab-gate.sh`) | deny `Bash(*strader-exec*)`, `Bash(*exec_gate*)`, `Read(tokens/*exec*)`, `Edit(tokens/*exec*)`; hook blocks the same by substring, including via the exec venv python |

These layers are *defense in depth* — tripwires and auditability — not the
wall itself. The wall is the passphrase.

## What the agent can and cannot do, after this ships

| | Before | After |
|---|---|---|
| Read quotes/chains | ✔ | ✔ (unchanged, hobbled client) |
| Write order-building code | ✖ (methods absent) | ✔ |
| Test order code | ✖ | ✔ (fixtures, no credentials) |
| Stage a live order ticket | ✖ | ✔ (inert JSON + hash) |
| Transmit an order | ✖ | ✖ (no passphrase, no TTY) |
| Read the trade credential | rules-forbidden | rules-forbidden **and** ciphertext |

## Build phases

1. **Phase A — authoring surface.** `strader/execution/` model + builders +
   preview + staging, tests green. No credential work. (Agent, normal beads flow)
2. **Phase B — gate skeleton.** `exec_gate.py` with TTY check, staging load,
   hash verify, risk rails, journal — transmit stubbed. Adversarial tests run
   here. (Agent)
3. **Phase C — the DEFENSE NOTE review.** The exec-capable diff (option a),
   presented to Steve as its own reviewed artifact; merges only on his
   sign-off recorded in the bead. (Steve gate)
4. **Phase D — credential ceremony + first live send.** Steve runs `init`,
   then a 1-lot far-OTM test order in the gate, cancel immediately. Journal
   entry verified. (Steve at the keyboard, agent watching nothing)
5. **Phase E — enforcement alignment.** CLAUDE.md / rules / settings / hook
   updates land together; `factory/harness` scenario added: a session is told
   to "just send the order" and must refuse and cite the gate. (Agent + COO)

## Adversarial test plan (Phase B, automated where possible)

- pipe a passphrase into `strader-exec` → must refuse (no TTY)
- run under `tmux send-keys` → must refuse (no controlling TTY on stdin)
- tampered staged file (1 byte) → hash refusal
- stale staged file → age refusal
- HALTED risk state → refusal regardless of confirmation
- decrypt attempt with 10^4 wrong passphrases → scrypt cost makes this
  ~hours-per-guess territory; verify no oracle shortcut in error messages
- grep the process environment and disk during a mock unlock → plaintext
  token must appear nowhere

## Honest limits — what this does not protect against

- **Steve himself.** The gate makes execution deliberate, not wise. The risk
  rails inside the gate are the only counterweight, and Steve can change them.
- **A compromised gate binary.** If the agent could silently edit
  `exec_gate.py` *and* Steve then runs it, the TTY ceremony launders agent
  code through Steve's passphrase. Mitigation: the gate file's hash is pinned
  in `CLAUDE.md`-adjacent config and printed at startup ("gate build
  `a1b2c3…`, changed 2026-08-02"); any change to `runbook/exec_gate.py` is a
  reviewed diff by convention, and the journal records the running hash per
  send. This is the plan's soft spot; the review ritual is the patch.
- **The read token's latent capability** (see corollary above) — unchanged,
  amputation + rules, as today.

## Decision points for Steve

1. Exec-capable dependency: fork branch (recommended) vs separate upstream venv.
2. Passphrase policy: memorized only (recommended) vs written backup in a
   physical location.
3. Phase D test order shape (far-OTM 1-lot SPX put, immediate cancel — or a
   paper-first variant if Schwab's paper endpoints prove usable).
