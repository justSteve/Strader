#!/usr/bin/env bash
# reauth-data.sh — re-authorise Schwab app 1 (market data), by hand, in this terminal.
#
# Alias: reauthData          (in ~/.bashrc; the twin is reauthTrade)
#
# What happens: the script prints a Schwab login link. Open it, log in, approve,
# then paste the full address the browser lands on at the "Redirect URL>" prompt
# and press Enter. Paste it straight away — Schwab's code expires within
# seconds, which is why this runs in your own terminal and not through an agent
# (2026-09-12: two codes died in the relay). The landing page shows an error;
# that is expected, only the address matters.
#
# Everything else — backup of the old token, shape check of the new grant, a
# live market-data call — is scripts/refresh_schwab_token.py, unchanged.
# Since execd stage 3 (st-p8k8): once /opt/execd/INSTALLED exists the service
# holds both grants and re-authorisation happens on its page —
# https://mydesk-1.tail89f676.ts.net/exec/ — so the script below answers with
# that address and exit 3 instead of minting a file nothing reads.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
exec .venv/bin/python3 scripts/refresh_schwab_token.py "$@"
