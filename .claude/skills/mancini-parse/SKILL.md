---
name: mancini-parse
description: Run the full Mancini letter parse — fetch, clean, in-session extraction, validate, publish, clipboard. Use when Steve asks to parse the Mancini letter, run the morning Mancini ritual, or types /mancini-parse. Strader owns this role exclusively.
---

# Mancini Parse — the complete morning procedure

[st-5ndx] This skill is the operational wrapper around the extraction contract.
The contract itself — extraction instructions, accuracy rules, and the exact
JSON shape — lives in `runbook/mancini/extraction-contract.md`. **Read that file
before extracting; do not work from memory.** The skill tells you the sequence;
the contract tells you how to extract.

A parse that stops early is incomplete. The procedure concludes at the
clipboard and the desk NAV, not at the JSON.

## Step 1 — Fetch and clean the letter

```bash
cd /root/projects/Strader && PYTHONPATH=. .venv/bin/python -c "
from runbook.mancini.fetch import fetch_latest
from runbook.mancini.clean import clean_newsletter
from pathlib import Path
name, raw = fetch_latest()
out = Path('/tmp/mancini-clean.txt')
out.write_text(clean_newsletter(raw), encoding='utf-8')
print(f'blob: {name}')
print(f'clean letter: {out}')
"
```

Blob only, never Gmail. The letter published the prior weekday targets the
*next* session's plan: the "Trade Plan <Weekday>" header names the plan-day.
Weekend resends carry the same plan — parse the newest blob, date the result
by plan-day.

## Step 2 — Extract, per the contract

Read `/tmp/mancini-clean.txt` and `runbook/mancini/extraction-contract.md`,
then write the extraction JSON to `/tmp/mancini-extraction.json` following the
contract exactly. Non-negotiables the validator will enforce anyway:

- Every price verbatim from the letter — never invented, rounded, or inferred.
- The explicit Supports/Resistances lists commonly hold 25–30 levels; capture
  every one. A near-empty `levels` array is a failure, not caution.
- Commentary = forward-looking conditional guidance only (Bull case / Bear
  case / In summary paragraphs), never past-session recap.

## Step 3 — Run the pipeline

```bash
cd /root/projects/Strader && PYTHONPATH=. .venv/bin/python -m runbook.mancini.run \
    --from-blob --date <plan-day> --extraction-json /tmp/mancini-extraction.json
```

This one command performs the whole back half: validation, deterministic
list-parity cross-check, commentary store, last-good parse file, overnight
interaction brief, Pine chart emit, desk publication, stable-title refresh,
and — because this is an interpretive parse — the Daily Payload lands on
Steve's Windows clipboard automatically. Never pass `--no-clip` for the live
morning parse; that flag is for backfills and renderer diagnostics only.

Gate note: the datastream gate expects the 06:30 CT corpus fill. If you are
parsing before 06:30 and the gate fails for that reason alone, that is the
known timing issue — surface it to Steve rather than silently passing
`--no-gate`.

## Step 4 — On failure, fix the extraction, never the check

- `FAILED: validation rejected` (rc=4) — a recorded price is not verbatim in
  the letter. Re-read the letter at the reported prices, correct the JSON,
  rerun. Do not delete a level just to pass; find what the letter actually says.
- `FAILED: interpretive parse omitted N listed level(s)` (rc=4) — the
  deterministic scrape found levels your extraction missed. Add them from the
  letter and rerun.
- Any failure keeps last-good artifacts published. Never hand-edit the desk
  doc or `parsed/<day>.json` around a failed validation.

## Step 5 — Verify the delivery

```bash
tmux -L moocity capture-pane -t steves-desk:Trading -p | grep -i mancini
```

The NAV must show `mancini-latest-es-plan.md` tagged `[today]`. Then render
the plan to the browser (desk HTML emit happens in the run; open it with
`powershell.exe Start-Process` on the desk file if Steve is reviewing now).
Report to Steve: plan-day, level count, commentary count, clipboard status,
and the desk link — name-first, link last.
