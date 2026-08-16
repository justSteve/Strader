#!/usr/bin/env bash
# deploy/install.sh — install (or refresh) Strader's systemd units. [st-n0qm.3]
#
#   bash deploy/install.sh            # copy every deploy/systemd/* into place, daemon-reload, enable
#   bash deploy/install.sh --diff     # show what would change, touch nothing
#   bash deploy/install.sh --start    # also (re)start the always-on services after installing
#
# Units are COPIED, not symlinked (matches how the collectors and the sentinel
# were installed on 08-13/08-16), so a repo checkout in a different state does
# not silently change what systemd runs. Timers stay under their own control:
# this script enables every unit that has an [Install] section and starts only
# the always-on services when asked — never a timer's service directly.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/systemd"
DST="/etc/systemd/system"
MODE="install"
START=0
for a in "$@"; do
    case "$a" in
        --diff) MODE="diff" ;;
        --start) START=1 ;;
        *) echo "usage: bash deploy/install.sh [--diff] [--start]" >&2; exit 2 ;;
    esac
done
[[ -d "$SRC" ]] || { echo "no $SRC" >&2; exit 2; }
changed=0
for f in "$SRC"/*.service "$SRC"/*.timer; do
    [[ -e "$f" ]] || continue
    name="$(basename "$f")"
    if [[ -e "$DST/$name" ]] && cmp -s "$f" "$DST/$name"; then
        continue
    fi
    changed=$((changed+1))
    if [[ "$MODE" == "diff" ]]; then
        echo "== $name"
        diff -u "$DST/$name" "$f" 2>/dev/null || true
    else
        install -m 0644 "$f" "$DST/$name"
        echo "installed $name"
    fi
done
if [[ "$MODE" == "diff" ]]; then
    echo "$changed unit(s) differ"; exit 0
fi
systemctl daemon-reload
for f in "$SRC"/*.service "$SRC"/*.timer; do
    [[ -e "$f" ]] || continue
    if grep -q '^\[Install\]' "$f"; then
        systemctl enable "$(basename "$f")" >/dev/null 2>&1 && echo "enabled $(basename "$f")"
    fi
done
if [[ $START -eq 1 ]]; then
    for u in strader-drill-bridge.service strader-footprint-feed.service strader-orderflow-sentinel.service; do
        [[ -e "$SRC/$u" ]] || continue
        systemctl restart "$u" && echo "started $u"
    done
fi
echo "$changed unit(s) changed"
