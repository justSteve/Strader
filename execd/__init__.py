"""execd — the live execution service: the one holder of the broker credential. [st-5qjq]

Steve's ruling, 2026-08-30 (st-l3s4): code executes live trades against the
API; the token is hidden from agents; pasting is not the long-term transport.
Design of record: ``docs/a2a/2026-08-30-coo-to-strader-live-execution-service-plan.md``.

What this package is:

- **One process** (``python -m execd``) that will hold the Schwab credential in
  memory after Steve unlocks it from its tailnet page, and nowhere else.
- **A narrow door** (``execd.api``): quote, chain, preview, place, cancel,
  orders, positions, flatten, status, stand-down, stop. Unlock, resume and
  re-auth are page-only and never on the API — an agent cannot arm it.
- **Bounds the service enforces itself** (``execd.bounds``), whatever the
  caller asks: SPX/SPXW options only, long premium only, a quantity cap, one
  position, a daily loss ceiling, the RTH window, a price band, idempotent
  intents, a preview before every send, and a STOP file that blocks entries
  and never blocks exits.
- **A broker-resident protective stop** on every fill (``execd.stops``), so a
  dead box still has a stop; the SPX-mark exit FD0 derives runs here while
  the box is alive.
- **An append-only journal** (``execd.journal``) stamped with the installed
  copy's sha — the audit that "trust the process" rests on.

What it is not, by construction: nothing here imports the repo's hobbled
``schwab`` library (``tests/execd/test_wall.py`` asserts it), and the source
tree is not the running copy — the installed service at ``/opt/execd`` is
put there only by ``deploy/install.sh``, which Steve runs.

Stage 1 (st-eznu) is everything above against ``MockBroker``; the Schwab
transport and the vault are stage 2 (st-w2nw); the unit, the page and the
migration are stage 3 (st-p8k8); the first live contract is stage 4
(st-k6gl), one lot with Steve at the STOP button.
"""

from __future__ import annotations

CT_TZ = "America/Chicago"
