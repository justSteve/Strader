# Estimated Mark Path — build plan

**`Estimated Mark Path` (`st-9hhc`)** · 2026-09-01 · handed to a Fable-grade model

## Why this exists

The blotter cannot be honest without it. Four blotter beads are open
(`st-uc23` Replay, `st-uaxf` Shadow, `st-08ru` Page — all assigned to COO) and
none has code. This one is Strader's and it is the substantive blocker:

> The refactor+blotter plan marks OPRA-less days by *"the ITM single tracks ES
> at +0.91."* **Measured, +0.91 is a Pearson CORRELATION** between the ES net
> move and the option's return at the close
> (`docs/measurement/final-hour-premium-vs-es-2026-08-29.md:31`) — **not
> premium points per ES point.** The actual conversion is §2 of that document,
> bins of ES points to median percent return, and it is **close-only: one
> number per day at 15:00.**

So on an estimated day a blotter row can honestly resolve **only a time exit**
— no intraday path, no stop, no target. That matters because the 0.30 cut
fires before the first +25% print on **82% of right-direction days when
measured from prints** (same document, line 90), and close to never on a
minute-resolution ES proxy. **A blotter pooling the two mark paths reports P&L
as a function of which days got an OPRA pull**, which is not a finding about
trading.

## The constraint that is larger than the bead says — measured 2026-09-01

Before writing anything, this was measured on `data/corpus/2026-08-14/`:

| file | CT coverage |
|---|---|
| `databento_opra.jsonl.gz` (trades/prints) | **13:00–15:00 only** — 151,380 rows in hour 13, 201,729 in hour 14 |
| `databento_opra_quotes.jsonl.gz` (NBBO) | **hour 14 only** — the 14:45–15:00 final fifteen, 21,885 rows |

**There is no option print path before 13:00 CT on any day** — not "on
OPRA-less days", on *every* day. So:

- The proxy can be calibrated and validated over **13:00–15:00 CT only**.
- Any use of it outside that window is **extrapolation and must be labelled
  so**. Do not silently apply a late-day calibration to a 10:15 fire.
- This bounds the blotter, and the bound belongs in the output rather than
  being discovered later by someone reading a P&L column.

Steve's actual plays are late-day (`knowledge/directional-gex-butterflies.md`,
`buying-movement-delta-first.md`), so the covered window is the one that
matters most — but say what is covered rather than implying the session.

## Deliverables

1. **`strader/marks/estimated.py`** (or the module path that fits the tree —
   look before choosing) — a per-minute ES→premium proxy: delta × ES move with
   a decay term for 0DTE theta through the session. Pure function of inputs,
   no network, deterministic.
2. **Calibration** over the 274 corpus days that carry
   `databento_opra_quotes.jsonl.gz`, restricted to 13:00–15:00 CT.
3. **Validation** against the actual print path, reporting:
   - close-mark residual, and
   - **the residual on STOP-FIRE TIMING specifically** — does the proxy fire a
     0.30 cut in the same minute the prints do? This is the number the bead
     asks for and the one the blotter depends on. A proxy with a good close
     mark and bad stop timing is useless here, and reporting only the close
     residual would hide exactly that.
4. **`docs/measurement/estimated-mark-path-<date>.md`** — the measurement
   write-up, with the coverage bound stated plainly.
5. **Tests** under `tests/` — deterministic, no network, pinning the decay
   term, the ES→premium conversion at known bins, and the coverage guard that
   refuses to extrapolate silently.

## Acceptance

- Two runs over one date range with unchanged code are **byte-identical**.
- Every claim in the write-up is labelled **measured** or **reasoned**.
- The write-up states the 13:00–15:00 coverage bound before any P&L-shaped
  number.
- Until this lands, estimated blotter rows carry `exit_reason=time` only and
  every aggregate splits by mark path — that is the current contract and the
  work does not get to relax it by assertion.

## Constraints

- **Never touch the Schwab API.** `.claude/rules/schwab-api-gate.md`; the
  `schwab-gate.sh` PreToolUse hook blocks any `.py` importing `schwab` or
  `broker_schwab`. This work needs neither.
- **No live market calls.** Corpus only, offline, repeatable.
- **Do not start `st-uc23`, `st-uaxf` or `st-08ru`** — assigned to COO. This
  bead is the prerequisite, not the blotter itself. If the work seems to
  require them, stop and say so rather than building into COO's lane.
- Timestamps render **CT, never UTC**.
- **`grep`, `find` and `rg` in the Bash tool are shims** — read
  `.claude/rules/shell-shim-hazards.md` before any recursive search. Never
  `find /`. Never `grep -oE` with bounded-repetition context.
- **Do not lead a Bash command with an assignment** (`VAR=value cmd`) — it
  matches no allow rule and prompts Steve. `.claude/rules/no-env-prefix-commands.md`.
- Commits cite `[st-9hhc]`. Stage explicit paths; never `git add -A` — peers
  share this tree.

## Read before starting

- `docs/measurement/final-hour-premium-vs-es-2026-08-29.md` — §1 correlations,
  §2 the close-only conversion, line 90 the 0.30-cut timing. **This is the
  source of truth for what +0.91 means.**
- `docs/a2a/2026-08-29-coo-to-strader-refactor-and-blotter-plan.md` — the
  blotter plan this unblocks.
- `strader/execution/fd0.py:55-96` — `Attempt.estimated`, the same meaning of
  "estimated" the blotter rows will carry.
- `scripts/measurement/final_hour_premium.py` — the existing leg machinery.
- `CLAUDE.md` and `.claude/rules/` — the standing rules.
