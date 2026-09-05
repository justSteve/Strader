---
type: runbook
title: "Schwab Auth Pattern"
description: "How Strader authenticates to Schwab: TWO developer apps — app 1 market data, which cannot trade, and app 2 Accounts and Trading — with token-file auth through the hobbled-readonly schwab-py fork (a submodule, installed editable) behind a gate key; each grant lives seven days and Steve renews BOTH in one sitting with scripts/refresh_schwab_token.py; callback URL has no trailing slash"
timestamp: 2026-09-05T08:45:00-05:00
metadata:
  originSessionId: ef56ec6d-2956-4bb4-bf28-0e6c19f41316
  graduated_from: project_schwab_auth_pattern.md
  source_type: project
  amended: "2026-09-05, st-p9mx (Two Schwab Apps) — the second registration. The
    portal refuses the Accounts and Trading product on app 1, so market data and
    trading are two apps with two grants and two walls; execd picks by endpoint
    family, and app 1's inability to trade is what lets its credential sit outside
    the arming lock. Supersedes the INCOMPLETE note this page carried that morning."
  rewritten: "2026-09-05, st-maav — Steve's answer to the legacy audit (Desk UPDATE on 20260904T153000). The 2026-05-12 page said schwab-py was installed from PyPI and exempt from fork doctrine, and named schwab-generate-token.py; none of that is true today."
---

> The 2026-09-05 ~11:00 CT note that this page described one app when there
> were two has been serviced: the second app is documented below, and the
> credential names it told you not to infer are now settled. The build is
> st-p9mx, *Two Schwab Apps*. Steve's own grant for app 2 is the one thing
> still outstanding — until it exists, `/trader/v1` has no working credential
> and the Trader API fixtures stay spec-derived.

**Two apps, and which one a call uses.** Steve has two registrations at
developer.schwab.com, and the split is permanent: the portal **will not** add
the Accounts and Trading product to app 1, so every `/trader/v1` call on it
answers 401 `no apiproduct match found` for good (Steve, 2026-09-05). App 1
carries market data — the two readers, the four schwab-stages crons, the corpus
token check, and `execd`'s quote and chain calls. App 2 carries Accounts and
Trading, and only `execd` calls it. Credentials: app 1 is `SCHWAB_API_KEY` /
`SCHWAB_APP_SECRET` / `SCHWAB_TOKEN_PATH`, unchanged and unlabelled; app 2 is
`SCHWAB_TRADING_API_KEY` / `SCHWAB_TRADING_APP_SECRET` /
`SCHWAB_TRADING_TOKEN_PATH`. The names are asymmetric on purpose — renaming
app 1's pair would touch every reader, four crons, the gate hook and the vault
file — so code says which app it means through `strader.settings.load_schwab_market`
and `load_schwab_trading` instead, and never reads an unlabelled name when it
is choosing. In `execd`, the app is derived from the request path
(`execd.schwab.app_for`) and never passed as an argument; an unmapped family is
refused rather than defaulted, so a request family added by hand later stops
on its first call instead of borrowing whichever credential was to hand.

**The consequence that matters beyond auth:** app 1 cannot trade, by Schwab's
enforcement rather than by our promise. So the execution service may hold its
credential from start-up, outside the arming lock, and answer quotes and chains
while it is LOCKED — which is what lets the 07:00 CT premarket jobs keep
running before Steve is awake to type a passphrase. Only app 2's credential
lives in the encrypted vault.

**Two grants, two walls, one sitting.** Each app has its own refresh token and
its own seven-day wall, and they drift apart if renewed separately. Renew
**both** whenever either is due — `scripts/refresh_schwab_token.py` for app 1,
the same script with `--trading` for app 2 — so there is one re-auth day a week
rather than two. Renewing a still-valid grant costs nothing and resets its
clock. Each is verified against the family it exists for: app 1 with a
market-data call, app 2 with `/trader/v1/accounts/accountNumbers`. Probing the
wrong family is the 2026-05-20 outage in which a good token was restored over.

**The library.** `lib/schwab-py` is a git submodule on the `hobbled-readonly` branch of the justSteve/schwab-py fork, installed editable into `.venv` (measured 2026-09-05: pip reports version 1.5.1 with editable project location `lib/schwab-py`). Account, order and transaction methods are physically removed — the DEFENSE NOTE in `lib/schwab-py/schwab/client/base.py` — and since 2026-09-01 the generic POST/PUT/DELETE path is gone too. It is a fork under [[fork-doctrine]], not an exemption from it. Upstream changes arrive as a reviewed diff onto the fork, never a pip upgrade.

**The client.** `broker_schwab/client.py` is the only factory. It refuses to build a client unless `~/.schwab_gate_key` exists (Steve creates it once; agents never touch it), reads `SCHWAB_API_KEY`, `SCHWAB_APP_SECRET` and `SCHWAB_TOKEN_PATH` (default `./tokens/schwab_token.json`, gitignored) from `.env`, and calls `client_from_token_file`. Never `easy_client`: it tries to open a browser and fails headless.

**The token.** Schwab refresh tokens live seven days. Renewal is `scripts/refresh_schwab_token.py`, run by Steve: a manual copy-paste OAuth flow (the script prints the authorization URL, he approves in any browser, pastes the redirect URL back), then two checks before it reports success — the written grant's shape (a refresh token must be present) and a cheap live market-data call. Two checks because on 2026-08-12 a mistyped redirect produced a 181-byte grant with no refresh token that still answered HTTP 200 for thirty minutes (st-r1b5). The `schwab-gate.sh` hook blocks agents from running any `.py` that imports `schwab`, this script included; only the two readers are excepted.

**Callback URL.** `SCHWAB_CALLBACK_URL` must match the app registration exactly, with no trailing slash. A trailing slash returns `invalid_client`.

**Health.** `scripts/schwab_token_health.py` writes `data/corpus/_schwab_token_health.json` from the 06:30 corpus job; its `actionable` flag is the gate for raising re-auth. With two apps configured it assesses both and reports the **nearer** wall, so the reminder never has to say which of two tokens it means. One plain reminder within a day or two of expiry, then early on the expiry day itself, never a countdown. The token dies at its stamped hour, mid-morning CT on its day, not at the close.

**What agents may run.** Only the two readers, via the venv python: `broker_schwab/readers/quote.py` and `broker_schwab/readers/chain.py`. Everything else Schwab-shaped is Steve's, through `./scripts/run.sh`.

**How to apply.** `invalid_grant` on an API call means the refresh token has expired: Steve runs the refresh script. An error naming `~/.schwab_gate_key` means the key is absent by design: do not create it. A token that has actually lapsed is a live failure and is reported at once whatever the date.
