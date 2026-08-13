# Rule: Schwab API Hard Gate

The agent CANNOT execute code that touches the live Schwab API. This is enforced mechanically at the permissions layer, not by policy alone.

## Enforcement layers

1. **Permissions deny list** — the hard denies hold: `schwab_gate_key`, `tokens/schwab*`, and the `.env` patterns are denied outright, and deny beats allow. But this layer does **not** gate interpreters. *(Corrected 2026-08-13, st-ad6p — this line previously claimed `python3`, `bash`, `sh`, `source`, `curl`, `touch`, `echo` are "NOT in the allow list" and that "any command using these prompts Steve." Measured false: `python3`, `bash`, `curl`, and `echo` are all auto-allowed via `Bash(<cmd> *)`. Only `sh`, `source`, and `touch` are genuinely absent.)* Treat the interpreter allow-list as wide open and rely on layer 2 for Schwab reach.
2. **PreToolUse hook** (PRIMARY as of 2026-08-13, st-ad6p) — `schwab-gate.sh` blocks a `.py` that imports `schwab` **or** `broker_schwab` (the two readers excepted), inline `-c` schwab, `python -m schwab`, writes to `tokens/`, and `scripts/run.sh`. It gates by what the code *reaches*, not by which directory it lives in — the old blanket ban on `scripts/` was written when that directory was Schwab code and now catches 65 files of which only 11 touch the API.

   It reads the command from `.tool_input.command` and **fails closed** on any other payload shape. This is load-bearing: from May to 2026-08-13 it read the bare `.command`, found nothing, and allowed everything, silently. Behaviour is pinned by `tests/test_schwab_gate_hook.py`, whose control case asserts that a command hidden at the top level is *refused* rather than acted on — run it before touching this hook.
3. **Gate key** — `~/.schwab_gate_key` is required by the client factory. Agent cannot create it (touch is not allowed).
4. **Credentials isolation** — `.env` is denied for Read and grep patterns targeting credentials are denied.

## What the agent CAN do

- Write and modify code in `broker_schwab/` and `scripts/`
- Run pytest: `python3 -m pytest` (explicitly allowed)
- **Read live market data** via pre-approved readers (auto-allowed):
  ```bash
  .venv/bin/python3 broker_schwab/readers/quote.py '$SPX' '/ES'
  .venv/bin/python3 broker_schwab/readers/chain.py '$SPX' --strikes 20
  .venv/bin/python3 broker_schwab/readers/chain.py '/ES' --dte 7
  ```
- Read and grep non-credential Schwab-related files
- Recommend what code Steve should run

## What the agent CANNOT do

- Execute arbitrary `python3`, `bash`, `sh`, `curl`, `source`, `echo`, or `touch` without Steve's approval
- Create `~/.schwab_gate_key` (hard-denied)
- Access `tokens/schwab*` (hard-denied)
- Read `.env` via any tool
- Modify reader scripts and execute them in the same session without Steve seeing the diff

## Permissible reader commands

Only these two scripts are auto-allowed, and only via the venv python:

| Command | What it does |
|---------|-------------|
| `.venv/bin/python3 broker_schwab/readers/quote.py [symbols...]` | Fetch quotes (default: $SPX /ES) |
| `.venv/bin/python3 broker_schwab/readers/chain.py [symbol] [opts]` | Fetch option chain with strike/expiry filters |

Both are read-only GET requests. No account data, no orders, no writes.

## Workflow

1. Agent writes/modifies code
2. Agent tests via `python3 -m pytest` (auto-allowed)
3. Agent reads live market data via `broker_schwab/readers/` (auto-allowed)
4. Steve reviews the diff
5. Steve runs non-reader scripts via `./scripts/run.sh <script.py>`
