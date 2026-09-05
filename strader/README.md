# Strader

The strategy layer for Strader. It carries the proven **datafeed infrastructure
by import** (never by copy) and holds only the strategy surface — config,
entities, and the `feeds/` re-export seam over the carried infra.

Originally built as the quarantined `strader2` package while the parent tree
was cleaned; folded in as the canonical `strader` package on 2026-07-02 once
that cleanup landed (COO bead `co-wu3n`).

Design of record: the greenfield plan `2026-06-29-strader2-greenfield-plan.md`
and the fold-in plan `2026-07-02-strader2-fold-in-plan.md`, both under
`docs/superpowers/specs/` **in the COO repo** (COO beads `co-r10h`, `co-wu3n`).
All 5 greenfield design decisions resolved 2026-06-30.

## Focus strategy

The **0DTE long single as a futures proxy** — *"a single is a futures contract on
its last day,"* delta-first, brief hold — triggered by **Carmine (Rosato) setups
recognized from the datafeed** (LVN / departure zones / order flow), with
**Mancini levels + Steve's eye as the touchstone**. Butterflies remain a manual,
reference-only play. There is no SPX↔ES converter (Steve handles the offset
manually) and no Carmine alert-ingestion (setups are recognized from the feed).

## Layout

```
strader/
  config.py     # strict, fail-fast config loader + validator (see below)
  feeds/        # the single seam over carried infra — lazy re-exports of
                #   market.ingest / market.corpus / broker_schwab / runbook.mancini
  tests/
```

## Config layer

`strader.config` supersedes the repo's per-script `_load_dotenv` helpers. It
exists because of the 2026-06-30 `.env` → `invalid_client` incident (an inline
`# comment` bled into `SCHWAB_API_KEY`). Two defenses:

1. **Authoritative parse** — `.env` is parsed strictly (inline comments + quotes
   stripped) and *overrides* any polluted process-environment value.
2. **Fail-fast validation** — every declared `Field` is validated at load; all
   problems are raised together in one `ConfigError` before any value reaches an
   API. `no_comment_residue` catches the exact original failure.
3. **Secrets out of the tree** (2026-09-05, credential estate convention of
   2026-08-25) — a `Field(secret=True)` value is read from the vault file named
   by `STRADER_SECRETS_FILE` in `.env` (default `/home/vault/Strader/env`, which
   must be mode 0600), never from `.env` itself. Precedence is vault file >
   `.env` > process environment. A secret found in `.env` is refused at load
   with a message naming the field. `.env` keeps the pointer and the
   non-secret settings; `.env.template` shows the layout. Every reader of a
   secret goes through `strader.settings` (`load_schwab`, `load_databento`,
   `load_gexbot`); `tests/scripts/test_*_env_routing.py` pin that no private
   `.env` parser comes back.

```python
from strader.config import Field, load, non_empty, no_comment_residue, no_whitespace, is_https_url

cfg = load([
    Field("SCHWAB_API_KEY",     secret=True, validators=(non_empty, no_comment_residue, no_whitespace)),
    Field("SCHWAB_APP_SECRET",  secret=True, validators=(non_empty, no_comment_residue)),
    Field("SCHWAB_CALLBACK_URL",             validators=(non_empty, no_comment_residue, is_https_url)),
    Field("SCHWAB_TOKEN_PATH",  required=False),
])
```

## Running tests

```bash
.venv/bin/python -m pytest strader/tests/
```
