# OWNERS — who is paged when a package breaks

Tranche 0 of the trading-code-estate architecture order (Desk, 2026-09-05 16:00;
ratified by Steve 2026-09-06). One line per top-level package: **owner**,
**second**, and the bead that last changed it. Push authority is unchanged —
COO's standing authority to commit here holds, and Steve is the principal
everywhere. Ownership is about *who is paged*, not who may write.

Measured 2026-09-06 against `git ls-files` (**981 tracked files in packages**,
991 including root files). The 08-12 census that said 1,103 is superseded: the
2026-09-06 prune took 136 files out of HEAD.

## The packages

| package | files | owner | second | last change | bead |
|---|---:|---|---|---|---|
| `docs/` | 254 | Strader | Desk | 2026-09-06 `0c2d24c` | st-hun6 |
| `tests/` | 190 | Strader | COO | 2026-09-06 `eea2f6a` | st-rfjg |
| `scripts/` | 125 | Strader | COO | 2026-09-06 `eea2f6a` | st-rfjg |
| `strader/` | 69 | Strader | COO | 2026-09-05 `12d246a` | st-p9mx |
| `runbook/` | 66 | Strader | COO | 2026-09-06 `eea2f6a` | st-rfjg |
| `market/` | 65 | Strader | COO | 2026-09-06 `eea2f6a` | st-rfjg |
| `archive/` | 56 | Strader | — | 2026-09-06 `eea2f6a` | st-rfjg |
| `knowledge/` | 35 | **Strader (single-home)** | COO | 2026-09-06 `3e2f926` | st-rfjg |
| `tools/` | 17 | Strader | COO | 2026-08-28 `b0c598d` | co-j9t1g |
| `deploy/` | 16 | **COO** | Strader | 2026-09-06 `eea2f6a` | st-rfjg |
| `footprint-icm/` | 16 | Strader | COO | 2026-09-04 `cb19dfe` | st-k75z |
| `.beads/` | 15 | **COO** | Strader | 2026-09-05 `938e3a4` | co-4q6cg |
| `.claude/` | 14 | **Steve lands** | Strader | 2026-09-06 `eea2f6a` | st-rfjg |
| `execd/` | 14 | **COO** | Strader | 2026-09-05 `7eb947f` | st-ilp9 |
| `broker_schwab/` | 9 | Strader | COO | 2026-09-06 `eea2f6a` | st-rfjg |
| `config/` | 4 | Strader | Steve (figures) | 2026-09-05 `480c393` | st-x3tx |
| `mancini/` | 3 | Strader | — | 2026-09-06 `eea2f6a` | st-rfjg |
| `present/` | 2 | Strader | — | 2026-09-06 `eea2f6a` | st-rfjg |
| `lib/` | 1 | Strader | Steve (gate key) | 2026-09-01 `45273b6` | st-c1af |
| `pine/` | 1 | Strader | — | 2026-08-04 `79f820d` | st-wqr |
| `.github/` | 1 | Strader | COO | 2026-08-05 `1f58336` | st-yyuz |
| `audit/`, `data/` | 2 | Strader | — | 2026-09-06 | st-rfjg |
| `.agents/`, `.codex/`, `.vscode/` | 6 | — | — | 2026-06/07 | — |

## What the bead column does and does not mean

It is the bead cited by the **most recent commit touching the package**, read
from that commit's `[...]` trailer. It is not a claim that the package's
*boundary* changed then. Eleven packages show `st-rfjg` for the same reason: one
prune touched them all on 2026-09-06.

Reading the bead out of commit prose instead of the trailer got eleven of these
wrong on the first pass — `eea2f6a` mentions `st-hrwe` in a sentence about a
wrapper and carries `[st-rfjg st-2opj st-sl1f st-hrwe]` at the end. The trailer
is the authorizing bead; prose is not.

## The three that are not Strader's, and why

- **`execd/` — COO.** It is the one credential holder on this box (st-5qjq) and
  COO built its Schwab transport (st-w2nw, st-ilp9). Strader is second because
  the gate rules and the readers live here.
- **`deploy/` — COO.** COO wrote and installed the capture units; Strader
  consumes them and now pins their collect window from
  `tests/scripts/test_gexbot_collect_window.py`.
- **`.beads/` — COO.** Dolt and schema repair are COO's domain by standing
  agreement; a corrupted DB is escalated, never repaired here.

**`.claude/` is nobody's to land but Steve's.** Hooks, settings and permissions
change only by his word (`.claude/rules/scope-and-permissions.md`). Strader
prepares and measures patches; two are waiting on him now (st-hun6, st-aseg).

## Freeze, per the order

No new files outside the target tree while tranches 0–3 are open. A new file in
`scripts/` needs a line in the tranche-3 classification table
(`docs/architecture/2026-09-06-tranche-0-census.md`) saying which class it is.

[st-c6ii]
