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
#
# WHERE THE GRANT GOES. Once the execution service is installed it is the one
# credential holder on this box, so the flow is handed to scripts/execd_reauth.py
# and the new grant is re-encrypted into the service's own vault under the
# passphrase you type — not into a token file under tokens/ that nothing reads
# any more. Between stage 3 (st-p8k8) and 2026-09-20 this handle did nothing but
# print the page's address and exit 3; st-bd2g gave it back its work. With no
# service installed the old file flow runs unchanged, and
# SCHWAB_REAUTH_FORCE_FILE=1 forces it either way.
#
# WHILE THE SERVICE IS ARMED it is holding the old grant in memory and does not
# keep your passphrase, so it cannot re-read the vault on its own: the run ends
# by telling you to LOCK and then UNLOCK on the page. While it is LOCKED — the
# ordinary case, before the first unlock of the day — there is nothing to do.
#
# Exit codes: 0 the grant was stored, notes on the screen or not; 1 refused
# before anything was sent; 2 the exchange or the live check failed and nothing
# was stored, so the old grant is still there to retry.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
exec .venv/bin/python3 scripts/refresh_schwab_token.py --trading "$@"
