#!/usr/bin/env bash
# deploy/install.sh — install (or refresh) Strader's systemd units. [st-n0qm.3]
#
#   bash deploy/install.sh            # copy every deploy/systemd/* into place, daemon-reload, enable
#   bash deploy/install.sh --diff     # show what would change, touch nothing
#   bash deploy/install.sh --start    # also (re)start the always-on services after installing
#   bash deploy/install.sh --execd    # ALSO install the execution service: user, dirs, code copy,
#                                     # venv, bounds, credentials (asks for the passphrase), unit,
#                                     # tailnet path — then start it and show its status [st-p8k8]
#   bash deploy/install.sh --execd --dry-run   # print the execd steps, touch nothing
#
# Units are COPIED, not symlinked (matches how the collectors and the sentinel
# were installed on 08-13/08-16), so a repo checkout in a different state does
# not silently change what systemd runs. Timers stay under their own control:
# this script enables every unit that has an [Install] section and starts only
# the always-on services when asked — never a timer's service directly.
#
# THE EXECD SECTION IS STEVE'S TO RUN, by the design of record (COO myDesk
# 2026-08-30 live-execution-service-plan §2): the running copy at /opt/execd is
# put there only by this script, so no agent can change what is actually
# transmitting without him running it. It is idempotent — run it again after
# every commit that touches execd/ to refresh the copy and restart the unit.
# It never overwrites a bounds file, a vault or a market credential that exists.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
SRC="$HERE/systemd"
DST="/etc/systemd/system"
MODE="install"
START=0
EXECD=0
DRY=0
for a in "$@"; do
    case "$a" in
        --diff) MODE="diff" ;;
        --start) START=1 ;;
        --execd) EXECD=1 ;;
        --dry-run) DRY=1 ;;
        *) echo "usage: bash deploy/install.sh [--diff] [--start] [--execd [--dry-run]]" >&2; exit 2 ;;
    esac
done
[[ -d "$SRC" ]] || { echo "no $SRC" >&2; exit 2; }

# ── execd: everything that must exist before its unit can start ──────────────
# Ordered so that a re-run does the least: each step checks before it acts.
EXECD_USER="execd"
EXECD_OPT="/opt/execd"
EXECD_ETC="/etc/execd"
EXECD_STATE="/var/lib/execd"
EXECD_VENV="$EXECD_OPT/venv"
EXECD_VAULT="$EXECD_STATE/vault.json"
EXECD_MARKET="$EXECD_STATE/market.json"
EXECD_BOUNDS="$EXECD_ETC/bounds.yaml"
EXECD_UNIT="strader-execd.service"
EXECD_PAGE_PORT=8779
EXECD_API_PORT=8778
EXECD_TAILNET_PATH="/exec"

say() { echo "execd: $*"; }
run() {
    # Every state-changing command in the execd section goes through here so
    # --dry-run can print the plan instead of doing it.
    if (( DRY )); then echo "  + $*"; else "$@"; fi
}

install_execd() {
    if [[ $EUID -ne 0 ]]; then
        echo "execd: the install creates a system user and writes under /opt, /etc and /var — run it as root." >&2
        exit 2
    fi
    say "installing from $REPO ($(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo 'no git'))"

    # 1. the service user
    if id "$EXECD_USER" >/dev/null 2>&1; then
        say "user $EXECD_USER exists"
    else
        run useradd --system --home-dir "$EXECD_STATE" --no-create-home --shell /usr/sbin/nologin "$EXECD_USER"
        say "user $EXECD_USER created"
    fi

    # 2. directories, with the ownership the design names:
    #    /opt/execd   root:execd 0750  the code — the service reads, never writes
    #    /etc/execd   root:execd 0750  Steve's bounds file — read only for the service
    #    /var/lib/execd execd:execd 0700  vault, market credential, journal, STOP
    run install -d -o root -g "$EXECD_USER" -m 0750 "$EXECD_OPT" "$EXECD_ETC"
    run install -d -o "$EXECD_USER" -g "$EXECD_USER" -m 0700 "$EXECD_STATE" "$EXECD_STATE/journal"

    # 3. the code: the execd/ package only, nothing else from the tree. rsync
    #    --delete keeps the copy exactly the package, so a module removed from
    #    the repo is removed from the running copy on the next install.
    run rsync -a --delete --exclude '__pycache__' --chown="root:$EXECD_USER" \
        --chmod=D0750,F0640 "$REPO/execd/" "$EXECD_OPT/execd/"
    local sha dirty stamp
    sha="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    dirty=""
    if [[ -n "$(git -C "$REPO" status --porcelain -- execd 2>/dev/null)" ]]; then dirty="-dirty"; fi
    stamp="$EXECD_OPT/INSTALLED"
    if (( DRY )); then
        echo "  + write $stamp (sha=$sha$dirty)"
    else
        printf 'sha=%s\ninstalled_at=%s\nfrom=%s\n' "$sha$dirty" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$REPO" > "$stamp"
        chown "root:$EXECD_USER" "$stamp"; chmod 0640 "$stamp"
    fi
    say "code copied to $EXECD_OPT/execd, stamped $sha$dirty"

    # 4. the venv: its own, because the repo venv lives under /root where the
    #    service user cannot follow. Pinned to deploy/execd-requirements.txt,
    #    which names the versions the suite passed on. Needs the network the
    #    first time; a re-run with everything satisfied is a few seconds.
    if [[ ! -x "$EXECD_VENV/bin/python" ]]; then
        run python3 -m venv "$EXECD_VENV"
        say "venv created at $EXECD_VENV"
    fi
    run "$EXECD_VENV/bin/pip" install --quiet --disable-pip-version-check -r "$HERE/execd-requirements.txt"
    run chown -R "root:$EXECD_USER" "$EXECD_VENV"
    run chmod -R o-rwx "$EXECD_VENV"
    say "venv satisfies execd-requirements.txt"

    # 5. the bounds file — seeded once, then Steve's. Never overwritten.
    if [[ -e "$EXECD_BOUNDS" ]]; then
        say "bounds file exists at $EXECD_BOUNDS (yours; not touched)"
    else
        run install -o root -g "$EXECD_USER" -m 0640 "$REPO/execd/bounds.example.yaml" "$EXECD_BOUNDS"
        say "bounds seeded at $EXECD_BOUNDS from execd/bounds.example.yaml"
    fi

    # 5b. the mode file — 'paper' or 'live'. Seeded as paper once, then Steve's.
    #     Absent also means paper; the service refuses any other word.
    EXECD_MODE="$EXECD_ETC/mode"
    if [[ -e "$EXECD_MODE" ]]; then
        say "mode file exists at $EXECD_MODE: $(tr -d '[:space:]' < "$EXECD_MODE") (yours; not touched)"
    else
        run bash -c "printf 'paper\n' > '$EXECD_MODE'"
        run chown root:"$EXECD_USER" "$EXECD_MODE"
        run chmod 0640 "$EXECD_MODE"
        say "mode seeded at $EXECD_MODE: paper (write 'live' there and re-run the install to go live)"
    fi

    # 6. the market credential (app 1, cannot trade): assembled from the repo's
    #    .env and the current market token, plain JSON 0600, execd-owned. Only
    #    when absent — after this the page's re-authorisation rewrites it.
    if [[ -e "$EXECD_MARKET" ]]; then
        say "market credential exists at $EXECD_MARKET (not touched)"
    else
        run "$REPO/.venv/bin/python" "$REPO/scripts/execd_market_credential.py" --out "$EXECD_MARKET"
        run chown "$EXECD_USER:$EXECD_USER" "$EXECD_MARKET"
        run chmod 0600 "$EXECD_MARKET"
        say "market credential written to $EXECD_MARKET"
    fi

    # 7. the vault (app 2, trading): asks for YOUR passphrase, twice, on this
    #    terminal. Only when absent. Skipped without a terminal — then run
    #    scripts/execd_vault_init.py yourself and re-run this script.
    if [[ -e "$EXECD_VAULT" ]]; then
        say "vault exists at $EXECD_VAULT (not touched)"
    elif [[ -t 0 ]]; then
        say "no vault yet — choose the passphrase now (8+ characters, spaces inside are fine)"
        run "$REPO/.venv/bin/python" "$REPO/scripts/execd_vault_init.py" --vault "$EXECD_VAULT"
        run chown "$EXECD_USER:$EXECD_USER" "$EXECD_VAULT"
        run chmod 0600 "$EXECD_VAULT"
        say "vault written to $EXECD_VAULT"
    else
        say "no vault and no terminal to ask for the passphrase — the service will start LOCKED"
        say "  and cannot be armed until you run:"
        say "  $REPO/.venv/bin/python $REPO/scripts/execd_vault_init.py --vault $EXECD_VAULT"
        say "  then: chown $EXECD_USER:$EXECD_USER $EXECD_VAULT && chmod 600 $EXECD_VAULT"
    fi

    # 8. the unit — installed by the generic loop below (it is in deploy/systemd),
    #    started here once everything it needs exists.
    if (( DRY )); then
        echo "  + systemctl daemon-reload; systemctl enable --now $EXECD_UNIT"
    else
        install -m 0644 "$SRC/$EXECD_UNIT" "$DST/$EXECD_UNIT"
        systemctl daemon-reload
        systemctl enable "$EXECD_UNIT" >/dev/null 2>&1 || true
        systemctl restart "$EXECD_UNIT"
        say "$EXECD_UNIT (re)started"
    fi

    # 9. the tailnet path for the page. tailscale serve keeps this across
    #    reboots; --bg makes it persistent. Tailnet only — never funnel.
    if command -v tailscale >/dev/null 2>&1; then
        run tailscale serve --bg --set-path "$EXECD_TAILNET_PATH" "http://127.0.0.1:$EXECD_PAGE_PORT$EXECD_TAILNET_PATH"
        say "page published at https://$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || echo '<tailnet host>')$EXECD_TAILNET_PATH/"
    else
        say "tailscale not on PATH — publish the page by hand:"
        say "  tailscale serve --bg --set-path $EXECD_TAILNET_PATH http://127.0.0.1:$EXECD_PAGE_PORT$EXECD_TAILNET_PATH"
    fi

    # 10. prove it answers. LOCKED is the right first answer.
    if (( DRY )); then
        echo "  + curl -s http://127.0.0.1:$EXECD_API_PORT/status"
        return
    fi
    local status
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        status="$(curl -s -m 2 "http://127.0.0.1:$EXECD_API_PORT/status" 2>/dev/null || true)"
        [[ -n "$status" ]] && break
        sleep 1
    done
    if [[ -z "$status" ]]; then
        say "the service did not answer on $EXECD_API_PORT within 10 s — read: journalctl -u $EXECD_UNIT -n 50"
        exit 1
    fi
    python3 - "$status" <<'PY'
import json, sys
st = json.loads(sys.argv[1])
arm = st.get("arming", {})
cred = st.get("credential") or {}
mk = cred.get("market") or {}
print(f"execd: answering — service {st.get('sha')}, arming {arm.get('state')}, STOP {'on' if arm.get('killed') else 'off'}")
print(f"execd: market-data grant wall {mk.get('refresh_wall', 'unknown')}" if mk.get("armed")
      else f"execd: market-data grant: {mk.get('detail', 'not loaded')}")
print("execd: next — open the page, enter the passphrase, watch the state turn ARMED")
PY
}

if (( EXECD )); then
    install_execd
fi

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
        if (( DRY )); then echo "  + install $name"; else
            install -m 0644 "$f" "$DST/$name"
            echo "installed $name"
        fi
    fi
done
if [[ "$MODE" == "diff" ]]; then
    echo "$changed unit(s) differ"; exit 0
fi
if (( DRY )); then echo "$changed unit(s) would change (dry run)"; exit 0; fi
systemctl daemon-reload
for f in "$SRC"/*.service "$SRC"/*.timer; do
    [[ -e "$f" ]] || continue
    if grep -q '^\[Install\]' "$f"; then
        systemctl enable "$(basename "$f")" >/dev/null 2>&1 && echo "enabled $(basename "$f")"
    fi
done
if [[ $START -eq 1 ]]; then
    # strader-orderflow-sentinel.service left this list 2026-09-08 (deploy/systemd/retired/, st-x3tx)
    for u in strader-drill-bridge.service strader-footprint-feed.service strader-profile-server.service; do
        [[ -e "$SRC/$u" ]] || continue
        systemctl restart "$u" && echo "started $u"
    done
fi
echo "$changed unit(s) changed"
