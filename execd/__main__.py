"""``python -m execd`` — run the service. [st-eznu, st-w2nw, st-p8k8]

Two brokers, and the choice is explicit or the process refuses to start: a
process called ``execd`` that started quietly and turned out to be talking to
nothing — or to the wrong thing — would be worse than one that would not
start.

    .venv/bin/python -m execd --mock --state-dir /tmp/execd --mock-unlock
    .venv/bin/python -m execd --schwab --vault /var/lib/execd/vault.json \
        --market-credential /var/lib/execd/market.json --state-dir /var/lib/execd

``--schwab`` (stage 2, st-w2nw) starts the service LOCKED against the real
Trader API. Nothing arms it but Steve's passphrase: on its tailnet page
(stage 3, st-p8k8, ``execd.page`` on a second loopback port that ``tailscale
serve`` publishes), or at this console with ``--unlock-stdin``, which reads
one line from standard input and never sees argv or the environment.
``--mock-unlock`` cannot arm a real broker: the guard is on the broker object,
not on the flag order.

Two loopback ports, two surfaces. ``127.0.0.1:8778`` is the narrow door the
trading code and the agents use — no unlock, no resume, no re-auth.
``127.0.0.1:8779`` is Steve's page, where those three live behind his
passphrase. Neither binds anything but the loopback; the page reaches the
tailnet only through ``tailscale serve``, never funnel.

The installed copy (``/opt/execd``, put there by ``deploy/install.sh`` which
Steve runs) is not a git checkout; ``install.sh`` leaves an ``INSTALLED``
stamp beside the package naming the commit it copied, and every journal line
carries that sha.
"""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path

import threading

from .api import BIND_HOST, BIND_PORT, create_app
from .bounds import load_bounds
from .broker import MockBroker
from .page import DEFAULT_CALLBACK_URL, PAGE_HOST, PAGE_PORT, CredentialFile, create_page
from .schwab import Credential, SchwabBroker, trading_payload
from .service import ExecService, ServiceConfig
from .paper import PaperBroker, read_mode
from .vault import BadPassphrase, Vault, VaultError
from .watch import INTERVAL_S as WATCH_INTERVAL_S, Watcher

#: Steve's mode file: ``paper`` or ``live``. Absent means paper.
DEFAULT_MODE_FILE = "/etc/execd/mode"

REPO = Path(__file__).resolve().parent.parent
DEFAULT_VAULT = "/var/lib/execd/vault.json"

#: Written by ``deploy/install.sh`` beside the installed package: one
#: ``key=value`` per line, ``sha=`` first. Absent in a checkout.
INSTALLED_STAMP = REPO / "INSTALLED"


def load_market_credential(path: str | Path) -> CredentialFile:
    """The market-data app's credential, read at start-up and held outside the
    arming lock (st-p9mx).

    It is a plain 0600 file owned by the service user, not a vault entry, and
    that is the design rather than an omission: it must be readable before Steve
    types anything, because the 07:00 premarket jobs run before he is awake. It
    is safe to hold that way because the credential cannot trade — Schwab
    refuses the whole ``/trader/v1`` family on that registration — and because
    nothing in this service routes a trading call to it.

    ``scripts/execd_market_credential.py`` writes the file the first time; the
    page rewrites it at each weekly re-authorisation (stage 3). Raises so the
    caller can decide whether to start without it."""
    holder = CredentialFile(path)
    holder.load()                     # shape-checked here, not on the first quote
    return holder


def installed_sha() -> str:
    """The sha of the copy that is running, stamped on every journal line.

    Every order this service sends is attributable to a commit. The installed
    copy at ``/opt/execd`` is not a checkout, so ``deploy/install.sh`` leaves
    an ``INSTALLED`` stamp there naming the commit (and ``-dirty`` if the tree
    it copied from had uncommitted changes); that is read first. In a checkout
    git answers. When neither can, the stamp reads ``unknown`` rather than
    lying about a version."""
    stamped = _stamped_sha()
    if stamped:
        return stamped
    try:
        out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = (out.stdout or "").strip()
    if out.returncode != 0 or not sha:
        return "unknown"
    # A dirty tree stamped with a clean sha is a journal attributing orders to
    # code that was never committed (audit finding 22, st-kh0l). The suffix is
    # the same one git describe uses, for the same reason.
    try:
        status = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return f"{sha}-unverified"
    if status.returncode != 0:
        return f"{sha}-unverified"
    return f"{sha}-dirty" if status.stdout.strip() else sha


def _stamped_sha() -> str | None:
    try:
        text = INSTALLED_STAMP.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "sha" and value.strip():
            return value.strip()
    return None


def may_mock_unlock(broker: object) -> bool:
    """May ``--mock-unlock`` arm this broker? Only the mock, ever.

    Structural, not positional: a flag that arms a REAL broker with no
    passphrase must be impossible, not merely unlikely (audit finding 17,
    st-kh0l). The check is on the object, so reordering ``main`` cannot
    quietly widen it."""
    return isinstance(broker, MockBroker)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="execd", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    which = p.add_mutually_exclusive_group()
    which.add_argument("--mock", action="store_true",
                       help="run against the deterministic MockBroker")
    which.add_argument("--schwab", action="store_true",
                       help="run against the Schwab Trader API; starts locked (stage 2)")
    p.add_argument("--vault", default=DEFAULT_VAULT,
                   help="the encrypted trading credential, for --schwab (default: %(default)s)")
    p.add_argument("--market-credential", default=None,
                   help="the market-data app's credential file (0600, owned by the "
                        "service user). Held outside the arming lock so quotes and "
                        "chains answer while the service is LOCKED; it cannot trade")
    p.add_argument("--unlock-stdin", action="store_true",
                   help="read the passphrase from standard input and arm at start — the "
                        "console path until the page exists (stage 3); never from an agent")
    p.add_argument("--state-dir", default="/var/lib/execd",
                   help="journal and STOP file live here (default: %(default)s)")
    p.add_argument("--bounds", default=None,
                   help="bounds YAML (default: /etc/execd/bounds.yaml, then the start values)")
    p.add_argument("--host", default=BIND_HOST, help=argparse.SUPPRESS)
    p.add_argument("--port", type=int, default=BIND_PORT,
                   help="loopback port (default: %(default)s)")
    p.add_argument("--mock-unlock", action="store_true",
                   help="arm the service with a fake credential — mock only, for local trials")
    p.add_argument("--page-port", type=int, default=PAGE_PORT,
                   help="loopback port for Steve's page — unlock, STOP, flatten, re-auth "
                        "(default: %(default)s); published by tailscale serve, never funnel")
    p.add_argument("--no-page", action="store_true",
                   help="do not serve the page (console trials; --unlock-stdin still works)")
    p.add_argument("--callback-url", default=DEFAULT_CALLBACK_URL,
                   help="the OAuth callback both Schwab apps are registered with, for the "
                        "page's re-authorisation (default: %(default)s)")
    p.add_argument("--mode-file", default=DEFAULT_MODE_FILE,
                   help="Steve's file saying 'paper' or 'live' (default: %(default)s; absent "
                        "means paper). Paper: every read and the broker's preview are live, "
                        "and orders fill in a simulated book against live quotes")
    p.add_argument("--watch-interval", type=float, default=WATCH_INTERVAL_S,
                   help="seconds between SPX-mark reads while a position or working entry "
                        "exists — the exit loop and the fill sweep (default: %(default)s; "
                        "0 turns the watcher off, for trials only)")
    return p


def _read_passphrase() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("execd vault passphrase: ")
    line = sys.stdin.readline()
    return line.rstrip("\r\n")


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:      # argparse's own refusal (e.g. --mock with --schwab)
        return 2 if exc.code else 0

    if not args.mock and not args.schwab:
        print("execd: choose a broker — --mock (deterministic, no network) or --schwab "
              "(the Trader API, starts locked). Neither is a default.", file=sys.stderr)
        return 2

    if args.host != BIND_HOST:
        # Not configurable, and refused rather than ignored. The fire server
        # carries the same rule for the same reason (scripts/fire_server.py).
        print(f"execd: refusing to bind {args.host} — this API is loopback-only.",
              file=sys.stderr)
        return 2

    if args.schwab and not Path(args.vault).is_file():
        if not args.market_credential:
            print(f"execd: --schwab needs the vault at {args.vault} and there is none. "
                  f"scripts/execd_vault_init.py writes one (Steve's passphrase).",
                  file=sys.stderr)
            return 2
        # With a market credential there is something real to serve — the
        # 07:00 reads — so the service starts, LOCKED for good until the vault
        # exists, and says so here and on its page rather than refusing.
        print(f"execd: no vault at {args.vault} — the service starts LOCKED and cannot "
              f"be armed until scripts/execd_vault_init.py writes one (Steve's "
              f"passphrase). Market reads still answer.", file=sys.stderr)

    bounds = load_bounds(args.bounds)
    try:
        mode = read_mode(args.mode_file)
    except (OSError, ValueError) as exc:
        print(f"execd: mode file unreadable — {exc}", file=sys.stderr)
        return 2
    config = ServiceConfig(state_dir=Path(args.state_dir), bounds=bounds,
                           sha=installed_sha(), mode=mode)
    broker = MockBroker() if args.mock else SchwabBroker(underlying=config.index_symbol,
                                                          roots=bounds.instruments)
    # `broker` stays the transport — bound, checked, printed below as before.
    # The service gets the paper wrapper over it when the mode says so: reads
    # and the preview pass through, orders never leave the box (st-k6gl).
    service_broker = (PaperBroker(broker, book_path=Path(args.state_dir) / "paper-book.json")
                      if mode == "paper" else broker)
    service = ExecService(service_broker, config)
    market: CredentialFile | None = None
    if isinstance(broker, SchwabBroker):
        broker.bind(service.arming)
        if args.market_credential:
            try:
                market = load_market_credential(args.market_credential)
                broker.bind_market(market.current)
            except (OSError, ValueError) as exc:
                print(f"execd: the market credential at {args.market_credential} "
                      f"is unusable: {exc}", file=sys.stderr)
                return 2
        else:
            # Not fatal — stage-2 console trials predate the file — but say what
            # is lost, because the loss is silent otherwise: reads fall back to
            # the trading credential and so stop working when the service locks.
            print("execd: no --market-credential; quotes and chains will use the "
                  "trading credential and will fail while the service is LOCKED.",
                  file=sys.stderr)

    if args.mock_unlock:
        if not may_mock_unlock(broker):
            print("execd: --mock-unlock arms only the mock broker. A real broker "
                  "is armed by Steve's passphrase, never by a flag.",
                  file=sys.stderr)
            return 2
        service.unlock({"mock": True})
        print("execd: armed with a MOCK credential — no broker is reachable.",
              file=sys.stderr)

    if args.unlock_stdin:
        if not isinstance(broker, SchwabBroker):
            print("execd: --unlock-stdin is for --schwab; the mock takes --mock-unlock.",
                  file=sys.stderr)
            return 2
        try:
            payload = trading_payload(Vault(args.vault).load(_read_passphrase()),
                                      args.state_dir)
            Credential.from_payload(payload)
        except BadPassphrase:
            print("execd: the vault did not open.", file=sys.stderr)
            return 3
        except (VaultError, ValueError) as exc:
            print(f"execd: the vault opened but cannot be used: {exc}", file=sys.stderr)
            return 3
        try:
            service.unlock(payload)
        except Exception as exc:  # a Refused (after the close) is reported, not hidden
            print(f"execd: unlock refused — {exc}", file=sys.stderr)
            return 3
        print(f"execd: armed until {service.arming.expires_at}; "
              f"refresh wall {broker.token_status().get('refresh_wall')}", file=sys.stderr)

    name = "mock" if args.mock else "schwab"
    print(f"execd {config.sha} on {BIND_HOST}:{args.port} — broker={name}, mode={mode}, "
          f"state={config.state_dir}, arming={service.arming.state.value}", file=sys.stderr)
    if mode == "paper":
        print("execd PAPER: quotes, chains, account and the broker's preview are live; "
              "orders fill in a simulated book against live quotes and never reach "
              f"Schwab. To go live: write 'live' to {args.mode_file} and restart.",
              file=sys.stderr)
    if args.watch_interval > 0:
        # The loop that watches a live position: fills picked up, the SPX-mark
        # exit fired. Without it a fill rests its broker stop and then sits
        # unwatched until the next place or flatten (st-k6gl).
        Watcher(service, interval_s=args.watch_interval).start()
        print(f"execd watch: every {args.watch_interval:g}s while exposed", file=sys.stderr)
    else:
        print("execd watch: OFF — no SPX-mark exit loop, no fill sweep", file=sys.stderr)
    if not args.no_page:
        page = create_page(service, vault=args.vault, market=market,
                           callback_url=args.callback_url,
                           state_dir=args.state_dir)
        threading.Thread(
            target=lambda: page.run(host=PAGE_HOST, port=args.page_port, threaded=True),
            name="execd-page", daemon=True).start()
        print(f"execd page on {PAGE_HOST}:{args.page_port} — publish it with: tailscale serve "
              f"--bg --set-path /exec http://{PAGE_HOST}:{args.page_port}/exec",
              file=sys.stderr)
    create_app(service).run(host=BIND_HOST, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
