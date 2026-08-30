"""``python -m execd`` — run the service. [st-eznu]

Stage 1 has one broker, the mock, so ``--mock`` is required and its absence is
a loud refusal rather than a default: a process called ``execd`` that started
quietly and turned out to be talking to nothing would be worse than one that
would not start. The Schwab transport arrives in stage 2 (st-w2nw) and takes
the flag's place; nothing about the bounds, the journal or the API changes when
it does, which is the point of the broker seam.

    .venv/bin/python -m execd --mock --state-dir /tmp/execd --mock-unlock

The service binds the loopback and nothing else. Steve's page — the surface
that takes the passphrase — is stage 3 and lives on the tailnet; there is no
route here that arms anything.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .api import BIND_HOST, BIND_PORT, create_app
from .bounds import load_bounds
from .broker import MockBroker
from .service import ExecService, ServiceConfig

REPO = Path(__file__).resolve().parent.parent


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
    return sha if out.returncode == 0 and sha else "unknown"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="execd", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mock", action="store_true",
                   help="run against the deterministic MockBroker (required in stage 1)")
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.mock:
        print("execd: stage 1 ships the mock broker only. Run with --mock.\n"
              "       The Schwab transport is st-w2nw (stage 2); nothing here can "
              "reach a broker until it lands.", file=sys.stderr)
        return 2

    if args.host != BIND_HOST:
        # Not configurable, and refused rather than ignored. The fire server
        # carries the same rule for the same reason (scripts/fire_server.py).
        print(f"execd: refusing to bind {args.host} — this API is loopback-only.",
              file=sys.stderr)
        return 2

    bounds = load_bounds(args.bounds)
    config = ServiceConfig(state_dir=Path(args.state_dir), bounds=bounds,
                           sha=installed_sha())
    broker = MockBroker()
    service = ExecService(broker, config)

    if args.mock_unlock:
        service.unlock({"mock": True})
        print("execd: armed with a MOCK credential — no broker is reachable.",
              file=sys.stderr)

    print(f"execd {config.sha} on {BIND_HOST}:{args.port} — broker=mock, "
          f"state={config.state_dir}, arming={service.arming.state.value}", file=sys.stderr)
    create_app(service).run(host=BIND_HOST, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
