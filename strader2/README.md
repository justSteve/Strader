# Strader2

The greenfield strategy layer for Strader. It carries the proven **datafeed
infrastructure by import** (never by copy) and rebuilds only the strategy surface
clean — leaving the ~80 files of factory/GC scaffolding in the parent tree
untouched and out of scope.

Design of record: `../docs/superpowers/specs/2026-06-29-strader2-greenfield-plan.md`
(COO bead `co-r10h`). All 5 design decisions resolved 2026-06-30.

## Focus strategy

The **0DTE long single as a futures proxy** — *"a single is a futures contract on
its last day,"* delta-first, brief hold — triggered by **Carmine (Rosato) setups
recognized from the datafeed** (LVN / departure zones / order flow), with
**Mancini levels + Steve's eye as the touchstone**. Butterflies remain a manual,
reference-only play. There is no SPX↔ES converter (Steve handles the offset
manually) and no Carmine alert-ingestion (setups are recognized from the feed).

## Layout

```
strader2/
  config.py     # strict, fail-fast config loader + validator (see below)
  feeds/        # the single seam over carried infra — lazy re-exports of
                #   market.ingest / market.corpus / broker_schwab / runbook.mancini
  tests/
```

## Config layer

`strader2.config` supersedes the repo's per-script `_load_dotenv` helpers. It
exists because of the 2026-06-30 `.env` → `invalid_client` incident (an inline
`# comment` bled into `SCHWAB_API_KEY`). Two defenses:

1. **Authoritative parse** — `.env` is parsed strictly (inline comments + quotes
   stripped) and *overrides* any polluted process-environment value.
2. **Fail-fast validation** — every declared `Field` is validated at load; all
   problems are raised together in one `ConfigError` before any value reaches an
   API. `no_comment_residue` catches the exact original failure.

```python
from strader2.config import Field, load, non_empty, no_comment_residue, no_whitespace, is_https_url

cfg = load([
    Field("SCHWAB_API_KEY",     secret=True, validators=(non_empty, no_comment_residue, no_whitespace)),
    Field("SCHWAB_APP_SECRET",  secret=True, validators=(non_empty, no_comment_residue)),
    Field("SCHWAB_CALLBACK_URL",             validators=(non_empty, no_comment_residue, is_https_url)),
    Field("SCHWAB_TOKEN_PATH",  required=False),
])
```

## Running tests

```bash
.venv/bin/python -m pytest strader2/tests/
```
