# Runbook — per-trading-day resource initialization

Stands up each strat's resources before the open. Pilot: **Mancini**.

Design spec (COO): `docs/superpowers/specs/2026-06-29-trading-day-runbook-design.md`
(bead `co-7tw8`); implementation epic `co-rc4t`. Architecture **direction C**: a
deterministic Python harness that calls an LLM as a *bounded function* only where
free-text interpretation is genuinely required — not a daily agent.

## Layout

```
runbook/
  datastream/
    gate.py        # co-i10h — pre-open health gate over data/corpus/<day>/manifest.json
  mancini/
    schema.py      # ParseResult / Level / Commentary / Trigger dataclasses
    listlevels.py  # st-ze6 — regex scrape of the explicit Supports/Resistances lists
    extraction-contract.md  # st-26q5 — the in-session prompt parse: instructions + JSON shape
    validate.py    # anti-hallucination: every price must appear verbatim in source
    store.py       # append-only JSONL commentary store (commentary/<day>.jsonl)
    parse.py       # orchestrate extract -> validate
    chart.py       # co-t1z9 — deterministic Pine overlay via existing pine_emitter
    run.py         # CLI: gate -> parse -> validate -> store + chart + brief
    commentary/    # generated: per-day JSONL (git-tracked)
    parsed/        # generated: per-day last-good ParseResult JSON (gitignored)
    charts/        # generated: per-day Pine overlay (gitignored)
```

## Daily run

```bash
# from the Strader repo root
python -m runbook.mancini.run --file /tmp/mancini-latest.txt
cat newsletter.txt | python -m runbook.mancini.run --date 2026-06-29
python -m runbook.mancini.run --file nl.txt --no-gate   # offline / no live feeds
```

Pipeline and exit codes:

| step | on failure |
|------|-----------|
| datastream gate (`#1`) | exit 2 — halt, keep last-good (no stale artifacts) |
| LLM extraction (`#2`) | exit 3 — alert, keep last-good (network / refusal) |
| validation (anti-hallucination) | exit 4 — reject, keep last-good (never publish suspect levels) |
| success | exit 0 — write `commentary/<day>.jsonl` + `parsed/<day>.json`, print brief |

## Configuration

- **Credential: none.** The runbook calls no model API. [st-26q5]
- **Interpretive leg:** an in-session prompt parse. An agent reads the letter,
  writes the extraction JSON per `mancini/extraction-contract.md`, and passes it
  with `--extraction-json`. `--model` records a label for who did the reading;
  omit it and the parse is stamped `in-session`.
- **Without an extraction:** the run publishes deterministic list levels alone
  with commentary flagged pending (hybrid mode), and will not clobber a richer
  parse already stored for that plan-day.
- **Newsletter source:** `--from-blob` fetches the newest letter from the COO
  email-ingress container via the Azure CLI (`mancini/fetch.py`, cached under
  `data/mancini-letters/`). `--file`/stdin also work.

## Anti-hallucination

This is financial data. The model is instructed to record only numbers that
literally appear in the newsletter and to attach a verbatim `source_quote` for
each. `validate.check()` then independently confirms every `Level.price` and
every commentary `anchor_price` appears verbatim in the raw text; any that don't
**reject the whole run** and the last-good artifacts are retained. The LLM is
never trusted to volunteer a number absent from the source. (Partner of the
enterprise no-confabulation rule.)

## Tests

```bash
./.venv/bin/python -m pytest tests/runbook/ -q
```

The live Anthropic call is injected, so the suite is deterministic and offline:
golden + poisoned fixtures for the validator, store round-trip, gate criteria,
parse assembly, and CLI gate/halt/keep-last-good paths.

## #3 chart — what's built vs manual

Per the feasibility verdict (spec addendum 2026-06-29), #3 splits:

- **Deterministic daily chart — BUILT** (`chart.py`): validated levels → Pine
  overlay via the existing `mancini/pine_emitter.py`, plus `apply_plan()` carrying
  both tradingview-mcp delivery paths (`pine_set_source` and per-line
  `draw_shape`). `run.py` writes `charts/<day>.pine` on success. The live apply
  step needs TradingView Desktop + the `tradingview-mcp` server (not headless-testable).
- **LuxAlgo Quant scaffold — MANUAL** (not automatable; no path to drive the Quant
  chat). The per-strat Quant prompt stays a version-controlled asset + TV-reset
  recovery recipe, surfaced by the Runbook for paste, not auto-delivered.

## Not yet built (follow-ons)

- **#9 morning brief surface** (`co-ewba`): render to a live tmux/URL surface
  (`run.py` currently prints a text brief — the mini version).
- **#10 intraday commentary highlighting** (`co-3qrw`): evaluate stored triggers
  against live price/time/regime.
- **Cron wiring for the interpretive leg**: the scheduled pre-open run has no
  agent in the loop, so it can only ever produce hybrid (levels-only) output.
  Getting commentary into the automated run means scheduling an agent session,
  not a script.
- The **per-strat Quant scaffold prompt** asset (manual authoring path).
