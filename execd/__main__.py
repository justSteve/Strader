"""``python -m execd`` — run the service. [st-eznu, st-w2nw]

Two brokers, and the choice is explicit or the process refuses to start: a
process called ``execd`` that started quietly and turned out to be talking to
nothing — or to the wrong thing — would be worse than one that would not
start.

    .venv/bin/python -m execd --mock --state-dir /tmp/execd --mock-unlock
    .venv/bin/python -m execd --schwab --vault /etc/execd/vault.json --state-dir /var/lib/execd

``--schwab`` (stage 2, st-w2nw) starts the service LOCKED against the real
Trader API. Nothing arms it but Steve's passphrase: on its tailnet page in
stage 3, or — until the page exists — typed at this console with
``--unlock-stdin``, which reads one line from standard input and never sees
argv or the environment. ``--mock-unlock`` cannot arm a real broker: the
guard is on the broker object, not on the flag order.

The service binds the loopback and nothing else. There is no route here that
arms anything.
"""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path

from .api import BIND_HOST, BIND_PORT, create_app
from .bounds import load_bounds
from .broker import MockBroker
from .schwab import Credential, SchwabBroker, trading_payload
from .service import ExecService, ServiceConfig
from .vault import BadPassphrase, Vault, VaultError

REPO = Path(__file__).resolve().parent.parent
DEFAULT_VAULT = "/etc/execd/vault.json"


def load_market_credential(path: str | Path) -> dict:
    """The market-data app's credential, read at start-up and held outside the
    arming lock (st-p9mx).

    It is a plain 0600 file owned by the service user, not a vault entry, and
    that is the design rather than an omission: it must be readable before Steve
    types anything, because the 07:00 premarket jobs run before he is awake. It
    is safe to hold that way because the credential cannot trade — Schwab
    refuses the whole ``/trader/v1`` family on that registration — and because
    nothing in this service routes a trading call to it.

    ``scripts/execd_market_credential.py`` writes the file. Raises so the
    caller can decide whether to start without it."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    Credential.from_payload(raw)      # shape-checked here, not on the first quote
    return raw


def installed_sha() -> str:
    """The sha of the copy that is running, stamped on every journal line.

    Every order this service sends is attributable to a commit. When the
    installed copy at ``/opt/execd`` is not a checkout, git says so and the
    stamp reads ``unknown`` rather than lying about a version."""
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
        print(f"execd: --schwab needs the vault at {args.vault} and there is none. "
              f"scripts/execd_vault_init.py writes one (Steve's passphrase).", file=sys.stderr)
        return 2

    bounds = load_bounds(args.bounds)
    config = ServiceConfig(state_dir=Path(args.state_dir), bounds=bounds,
                           sha=installed_sha())
    broker = MockBroker() if args.mock else SchwabBroker(underlying=config.index_symbol)
    service = ExecService(broker, config)
    if isinstance(broker, SchwabBroker):
        broker.bind(service.arming)
        if args.market_credential:
            try:
                market = load_market_credential(args.market_credential)
                broker.bind_market(lambda: market)
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
            payload = trading_payload(Vault(args.vault).load(_read_passphrase()))
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
    print(f"execd {config.sha} on {BIND_HOST}:{args.port} — broker={name}, "
          f"state={config.state_dir}, arming={service.arming.state.value}", file=sys.stderr)
    create_app(service).run(host=BIND_HOST, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
