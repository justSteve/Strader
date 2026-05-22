# Rule: Schwab API Hard Gate

The agent CANNOT execute code that touches the live Schwab API. This is enforced mechanically at the permissions layer, not by policy alone.

## Enforcement layers

1. **Permissions deny list** (primary) — `python3`, `bash`, `sh`, `source`, `curl`, `touch`, `echo` are NOT in the allow list. Any command using these prompts Steve for approval. `schwab_gate_key` and `tokens/schwab*` patterns are hard-denied.
2. **PreToolUse hook** (secondary) — `schwab-gate.sh` catches schwab imports in `.py` files and inline `-c` commands as belt-and-suspenders.
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
