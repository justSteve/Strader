---
type: runbook
title: "Schwab Auth Pattern"
description: "How Strader authenticates to Schwab: token-file auth through the hobbled-readonly schwab-py fork (a submodule, installed editable) behind a gate key; the refresh token lives seven days and Steve renews it by hand with scripts/refresh_schwab_token.py; callback URL has no trailing slash"
timestamp: 2026-09-05T08:45:00-05:00
metadata:
  originSessionId: ef56ec6d-2956-4bb4-bf28-0e6c19f41316
  graduated_from: project_schwab_auth_pattern.md
  source_type: project
  rewritten: "2026-09-05, st-maav — Steve's answer to the legacy audit (Desk UPDATE on 20260904T153000). The 2026-05-12 page said schwab-py was installed from PyPI and exempt from fork doctrine, and named schwab-generate-token.py; none of that is true today."
---

**The library.** `lib/schwab-py` is a git submodule on the `hobbled-readonly` branch of the justSteve/schwab-py fork, installed editable into `.venv` (measured 2026-09-05: pip reports version 1.5.1 with editable project location `lib/schwab-py`). Account, order and transaction methods are physically removed — the DEFENSE NOTE in `lib/schwab-py/schwab/client/base.py` — and since 2026-09-01 the generic POST/PUT/DELETE path is gone too. It is a fork under [[fork-doctrine]], not an exemption from it. Upstream changes arrive as a reviewed diff onto the fork, never a pip upgrade.

**The client.** `broker_schwab/client.py` is the only factory. It refuses to build a client unless `~/.schwab_gate_key` exists (Steve creates it once; agents never touch it), reads `SCHWAB_API_KEY`, `SCHWAB_APP_SECRET` and `SCHWAB_TOKEN_PATH` (default `./tokens/schwab_token.json`, gitignored) from `.env`, and calls `client_from_token_file`. Never `easy_client`: it tries to open a browser and fails headless.

**The token.** Schwab refresh tokens live seven days. Renewal is `scripts/refresh_schwab_token.py`, run by Steve: a manual copy-paste OAuth flow (the script prints the authorization URL, he approves in any browser, pastes the redirect URL back), then two checks before it reports success — the written grant's shape (a refresh token must be present) and a cheap live market-data call. Two checks because on 2026-08-12 a mistyped redirect produced a 181-byte grant with no refresh token that still answered HTTP 200 for thirty minutes (st-r1b5). The `schwab-gate.sh` hook blocks agents from running any `.py` that imports `schwab`, this script included; only the two readers are excepted.

**Callback URL.** `SCHWAB_CALLBACK_URL` must match the app registration exactly, with no trailing slash. A trailing slash returns `invalid_client`.

**Health.** `scripts/schwab_token_health.py` writes `data/corpus/_schwab_token_health.json` from the 06:30 corpus job; its `actionable` flag is the gate for raising re-auth. One plain reminder within a day or two of expiry, then early on the expiry day itself, never a countdown. The token dies at its stamped hour, mid-morning CT on its day, not at the close.

**What agents may run.** Only the two readers, via the venv python: `broker_schwab/readers/quote.py` and `broker_schwab/readers/chain.py`. Everything else Schwab-shaped is Steve's, through `./scripts/run.sh`.

**How to apply.** `invalid_grant` on an API call means the refresh token has expired: Steve runs the refresh script. An error naming `~/.schwab_gate_key` means the key is absent by design: do not create it. A token that has actually lapsed is a live failure and is reported at once whatever the date.
