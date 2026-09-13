#!/usr/bin/env bash
# reauth-trade.sh — re-authorise Schwab app 2 (accounts and trading), by hand, in this terminal.
#
# Alias: reauthTrade         (in ~/.bashrc; the twin is reauthData)
#
# Same flow as reauth-data.sh: open the printed link, log in, approve, paste the
# full landing address at the "Redirect URL>" prompt straight away — Schwab's
# code expires within seconds. The landing page shows an error; that is
# expected. Do both apps in one sitting so their seven-day walls stay on the
# same day.
#
# Backup, shape check and the live /trader/v1 call are
# scripts/refresh_schwab_token.py --trading, unchanged.
# Since execd stage 3 (st-p8k8): once /opt/execd/INSTALLED exists the service
# holds both grants and re-authorisation happens on its page —
# https://mydesk-1.tail89f676.ts.net/exec/ — so the script below answers with
# that address and exit 3 instead of minting a file nothing reads.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
exec .venv/bin/python3 scripts/refresh_schwab_token.py --trading "$@"
