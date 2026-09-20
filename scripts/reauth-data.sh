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
#
# WHERE THE GRANT GOES. Once the execution service is installed it is the one
# credential holder on this box, so the flow is handed to scripts/execd_reauth.py
# and the new grant is written into the service's own store, not into a token
# file under tokens/ that nothing reads any more. Between stage 3 (st-p8k8) and
# 2026-09-20 this handle did nothing but print the page's address and exit 3;
# st-bd2g gave it back its work. With no service installed the old file flow
# runs unchanged, and SCHWAB_REAUTH_FORCE_FILE=1 forces it either way.
#
# Exit codes: 0 the grant was stored, notes on the screen or not; 1 refused
# before anything was sent; 2 the exchange or the live check failed and nothing
# was stored, so the old grant is still there to retry. Anything left to do
# about the running service is said in words in the last lines of the run.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
exec .venv/bin/python3 scripts/refresh_schwab_token.py "$@"
