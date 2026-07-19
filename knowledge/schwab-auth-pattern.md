---
type: runbook
title: "Schwab Auth Pattern"
description: "Schwab API auth pattern — token-file auth, no trailing slash on callback, schwab-py exempt from fork doctrine"
timestamp: 2026-05-12T08:52:46-05:00
metadata:
  originSessionId: ef56ec6d-2956-4bb4-bf28-0e6c19f41316
  graduated_from: project_schwab_auth_pattern.md
  source_type: project
---

Schwab API auth is working as of 2026-05-12. Key decisions:

- **Auth method:** `client_from_token_file` — never `easy_client` (tries to open a browser, fails headlessly)
- **Token generation:** `schwab-generate-token.py` with `client_from_manual_flow` fallback — must run interactively in a real terminal
- **Callback URL:** `https://127.0.0.1:8182` — NO trailing slash. Schwab requires exact match; trailing slash causes `invalid_client`
- **schwab-py:** Installed from PyPI (1.5.1), exempt from [[fork-doctrine]] in this repo. Future API work belongs in a separate repo.
- **Token path:** `./tokens/schwab_token.json` (gitignored)

**Why:** The schwab-py fork (justSteve/schwab-py) has local divergence but we don't plan to extend it here. Strader consumes the API; a dedicated repo is the right home for any future API-layer work.

**How to apply:** If upstream schwab-py changes auth behavior (new versions break token flow, endpoint changes), revisit and understand why before upgrading. Retain this auth pattern unless there's a clear reason to change it.
