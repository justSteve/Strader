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

It never acts because of the time of day. Until 2026-09-24 every pass
also ran a 14:55 CT close-out; Steve: "omg - never ever place that kind of
restriction on me ... As 0DTE trades, if i don't close them, they expire.
flat. But I will _never ask that you do it automatically." It is gone, and
the 2026-09-18 reading of "9j8e is flat" as a request for it was wrong.
[co-8mb1z]

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
INTERVAL_S = 3.0
#: A pass within this long of the last reconcile (the open page's poll runs
#: one too) reads the mark but does not ask the broker again (st-5n3s).
RECONCILE_MIN_GAP_S = 2.5
#: How often the watcher looks for exposure when there is none.
IDLE_INTERVAL_S = 30.0
#: A pass the account stream rang for reconciles unless one ran this recently.
#: Schwab sends an order's events in a burst (eleven in ~20 s for one cancelled
#: TOS order, 2026-09-30); the Event coalesces a burst, this spaces the GETs.
RING_RECONCILE_GAP_S = 1.0


class Watcher:
    def __init__(self, service: ExecService, *, interval_s: float = INTERVAL_S,
                 idle_interval_s: float = IDLE_INTERVAL_S,
                 sleep: Callable[[float], None] | None = None) -> None:
        self.service = service
        self.interval_s = interval_s
        self.idle_interval_s = idle_interval_s
        self._stop = threading.Event()
        #: set by the account-activity stream (st-8bls): an event at the
        #: broker ends the wait early. Tests inject ``sleep`` and ring by hand.
        self._wake = threading.Event()
        self._sleep = sleep or self._wait
        self._broker_down = False
        self.passes = 0

    # ── the doorbell ─────────────────────────────────────────────────────
    def ring(self, types: Any = None) -> None:
        """Something happened at the broker — look now, not at the next beat.
        Called from the stream's thread; only sets an Event. [st-8bls]"""
        self._wake.set()

    def _wait(self, timeout: float) -> None:
        self._wake.wait(timeout)

    # ── one pass ─────────────────────────────────────────────────────────
    def once(self) -> dict[str, Any]:
        """One pass. Returns what it did, for the tests and the log."""
        self.passes += 1
        rung = self._wake.is_set()
        self._wake.clear()
        svc = self.service
        if svc.arming.state is ArmState.LOCKED:
            return {"skipped": "locked"}
        out: dict[str, Any] = {}
        if not svc.has_exposure():
            return {**out, "skipped": "flat"}
        try:
            rec = svc.reconcile_if_stale(RING_RECONCILE_GAP_S if rung
                                         else RECONCILE_MIN_GAP_S) or {}
            if rung:
                out["rung"] = True
            out["reconcile"] = rec
            if isinstance(rec, dict) and rec.get("error"):
                # reconcile reports a broker failure rather than raising it;
                # the mark would come from the same broker, so this pass ends.
                raise BrokerError(str(rec["error"]))
            spx = svc.spx_mark()
            out["spx"] = spx
            out["observe"] = svc.observe(spx)
            # the trailing stop (st-s1y1): after the exit loop, so a position
            # the mark just closed is not trailed
            trailed = svc.trail()
            if trailed:
                out["trail"] = trailed
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
        self._wake.set()
