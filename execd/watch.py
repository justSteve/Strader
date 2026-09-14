"""The watcher — the loop that keeps a live position watched. [st-k6gl]

The design (2026-08-30, §3) says: *while the box is alive the service runs the
SPX-mark exit loop; the resting stop at the broker is for when it is not.* The
routes for that loop existed from stage 1 — ``POST /observe`` takes the index
mark and fires FD0's SPX-level exit, ``POST /poll-fills`` books a stop that
fired at the broker — and through stage 3 nothing in the tree called either
one. A fill would have rested its protective stop and then sat, unwatched by
the accurate loop, until something happened to call ``place`` or ``flatten``
(both reconcile first). Found while wiring stage 4's rehearsal, when "the full
life cycle" had to be walked end to end.

So this: a thread inside the service that, whenever the service holds a
position or a working entry, reconciles against the broker (picks up fills,
notices what closed) and feeds the SPX mark to :meth:`ExecService.observe`.
Every few seconds while exposed; a slow idle check otherwise; nothing at all
while LOCKED, because with no credential in memory there is nothing to ask
the broker with and no exit can be sent anyway.

What it does not do: it never opens anything. ``observe`` and ``reconcile``
are exit-class — they can only close, and only what the journal and the broker
agree is held. A broker outage is journaled once per outage and retried; an
unexpected exception is logged and the loop goes on, because the loop dying
quietly is the failure this module exists to prevent.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .arming import ArmState
from .broker import BrokerError
from .service import ExecService, Refused

log = logging.getLogger("execd.watch")

#: How often the mark is read while a position or working entry exists.
INTERVAL_S = 5.0
#: How often the watcher looks for exposure when there is none.
IDLE_INTERVAL_S = 30.0


class Watcher:
    def __init__(self, service: ExecService, *, interval_s: float = INTERVAL_S,
                 idle_interval_s: float = IDLE_INTERVAL_S,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.service = service
        self.interval_s = interval_s
        self.idle_interval_s = idle_interval_s
        self._sleep = sleep
        self._stop = threading.Event()
        self._broker_down = False
        self.passes = 0

    # ── one pass ─────────────────────────────────────────────────────────
    def once(self) -> dict[str, Any]:
        """One pass. Returns what it did, for the tests and the log."""
        self.passes += 1
        svc = self.service
        if svc.arming.state is ArmState.LOCKED:
            return {"skipped": "locked"}
        if not svc.has_exposure():
            return {"skipped": "flat"}
        out: dict[str, Any] = {}
        try:
            rec = svc.reconcile()
            out["reconcile"] = rec
            if isinstance(rec, dict) and rec.get("error"):
                # reconcile reports a broker failure rather than raising it;
                # the mark would come from the same broker, so this pass ends.
                raise BrokerError(str(rec["error"]))
            spx = svc.spx_mark()
            out["spx"] = spx
            out["observe"] = svc.observe(spx)
        except BrokerError as exc:
            if not self._broker_down:
                svc.journal.record("error", kind="watch", detail=f"broker: {exc}")
                log.warning("watch: broker unreachable — %s", exc)
            self._broker_down = True
            return {**out, "error": str(exc)}
        except Refused as exc:
            # An exit the service would not send (LOCKED between the check and
            # the send, say). Journaled by the service; noted here.
            return {**out, "refused": str(exc)}
        if self._broker_down:
            svc.journal.record("watch", detail="broker back")
            self._broker_down = False
        return out

    # ── the loop ─────────────────────────────────────────────────────────
    def run(self) -> None:
        log.info("watch: started (every %.0fs while exposed, %.0fs idle)",
                 self.interval_s, self.idle_interval_s)
        while not self._stop.is_set():
            try:
                result = self.once()
            except Exception:  # noqa: BLE001 — the loop must outlive any one pass
                log.exception("watch: pass failed; continuing")
                result = {"error": "exception"}
            exposed = "skipped" not in result
            self._sleep(self.interval_s if exposed else self.idle_interval_s)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run, name="execd-watch", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()
