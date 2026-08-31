"""The journal — append-only, one file a trading day. [st-eznu]

This is the audit that "trust the process" rests on (design §3). Every request
the service receives, every refusal with the bound that caused it, every
preview, placement, fill, exit, unlock, stand-down and STOP goes in, stamped
with the sha of the installed copy that wrote it. On the first live day it is
read back against Schwab's own order history before there is a second.

Two properties it must have and a plain log would not:

**Append-only, flushed.** Each line is written and ``fsync``'d before the call
returns. A service that acknowledged an order it had not yet recorded would,
after a crash, come back not knowing what it had sent — and this is a machine
that has already lost a run to an OOM kill this month.

**The day's state is derived from it, not held beside it.** ``day_state()``
rebuilds open positions, realized loss and attempts used by reading the file.
There is no counter in memory to drift, and a restart mid-session recovers the
ceiling rather than resetting it — which is the whole point of a ceiling that
holds when Steve is not watching.

Losses only debit. A winning trade does not buy back an attempt or raise the
ceiling; the budget is a bound on how much of the day can go wrong, not a
running P&L. That is FD0's ``Budget`` semantics
(``strader/execution/compose.py:131-148``), carried here unchanged.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .bounds import CT, DayState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Journal:
    """One directory of ``YYYY-MM-DD.jsonl`` files, named by Central date."""

    def __init__(self, directory: str | Path, sha: str = "unknown",
                 clock: Callable[[], datetime] = _utcnow) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.sha = sha or "unknown"
        self.clock = clock
        self._lock = threading.Lock()

    # ── writing ──────────────────────────────────────────────────────────
    def path_for(self, day: date | None = None) -> Path:
        d = day or self.today()
        return self.dir / f"{d.isoformat()}.jsonl"

    def today(self) -> date:
        return self.clock().astimezone(CT).date()

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        """Append one event and return the line as written."""
        now = self.clock()
        line: dict[str, Any] = {
            "ts": now.isoformat(),
            "ts_ct": now.astimezone(CT).strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "sha": self.sha,
        }
        line.update({k: _plain(v) for k, v in fields.items()})
        payload = json.dumps(line, separators=(",", ":"), sort_keys=False)
        path = self.path_for(now.astimezone(CT).date())
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(payload + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        return line

    # ── reading ──────────────────────────────────────────────────────────
    def read(self, day: date | None = None) -> list[dict[str, Any]]:
        path = self.path_for(day)
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                # A truncated last line is what a kill mid-write looks like.
                # Surface it as data rather than raising: the rest of the day
                # is still the audit, and a journal that cannot be read after
                # a crash is not an audit at all.
                out.append({"event": "unreadable", "line_no": n, "raw": raw})
        return out

    def days(self) -> list[date]:
        out: list[date] = []
        for p in sorted(self.dir.glob("*.jsonl")):
            try:
                out.append(date.fromisoformat(p.stem))
            except ValueError:
                continue
        return out

    def find(self, intent_id: str, day: date | None = None) -> list[dict[str, Any]]:
        """Every line an intent produced — the idempotency lookup."""
        return [e for e in self.read(day) if e.get("intent_id") == intent_id]

    def tail(self, n: int = 20, day: date | None = None) -> list[dict[str, Any]]:
        return self.read(day)[-n:]

    def events(self, *names: str, day: date | None = None) -> list[dict[str, Any]]:
        wanted = set(names)
        return [e for e in self.read(day) if e.get("event") in wanted]

    # ── derived state ────────────────────────────────────────────────────
    def day_state(self, day: date | None = None) -> DayState:
        """Rebuild the day from its own record. See the module docstring.

        Three kinds of risk are counted, not one, and the reason is finding 1 of
        the 2026-08-30 audit (st-v7oa). Counting only fills made the day's state
        an account of what *filled*, while the service transmits on what was
        *requested*; a limit resting at the broker held none of the day's budget
        and so could be repeated without limit.

        **Filled entries** are the ordinary case: an attempt spent and a slot
        taken, released when the position closes with nothing remaining.

        **Working entries** — placed, acknowledged, not yet resolved — hold an
        attempt and a slot too, because a resting buy becomes a position the
        moment the book comes to it and the service is not watching the book.
        ``entry_resolved`` releases them: filled ones are then counted by their
        own fill line, cancelled and rejected ones cost nothing, which keeps a
        broker that refuses twice from spending Steve's day.

        **Adopted positions** — found at the broker and never opened here — hold
        a slot but not an attempt. They are real risk, so they close the entry
        door; they are not this service's sends, so they do not spend its
        budget.
        """
        opened = 0
        closed = 0
        realized_loss = 0.0
        pending: set[str] = set()      # entry orders live at the broker
        adopted: set[str] = set()      # symbols held that this service did not open
        for e in self.read(day):
            event = e.get("event")
            if event == "working" and e.get("kind") == "entry":
                if order_id := str(e.get("order_id") or ""):
                    pending.add(order_id)
            elif event == "entry_resolved":
                pending.discard(str(e.get("order_id") or ""))
            elif event == "filled" and e.get("kind") == "entry":
                opened += 1
            elif event == "position_adopted":
                if symbol := str(e.get("symbol") or ""):
                    adopted.add(symbol)
            elif event == "position_gone":
                adopted.discard(str(e.get("symbol") or ""))
            elif event == "closed":
                # A partial close carries what is still open. The loss on the
                # part that closed debits the ceiling immediately — waiting for
                # the rest would let a bad day spend more than Steve allowed —
                # but the position slot is only freed when nothing is left.
                symbol = str(e.get("symbol") or "")
                if not e.get("remaining_qty"):
                    if symbol in adopted:
                        adopted.discard(symbol)
                    else:
                        closed += 1
                pnl = e.get("pnl_usd")
                if isinstance(pnl, (int, float)) and pnl < 0:
                    realized_loss += -float(pnl)
        return DayState(
            open_positions=max(0, opened - closed) + len(pending) + len(adopted),
            realized_loss_usd=round(realized_loss, 2),
            attempts_used=opened + len(pending),
        )

    def __iter__(self) -> Iterator[dict[str, Any]]:  # pragma: no cover - convenience
        return iter(self.read())


def _plain(v: Any) -> Any:
    """Make a value JSON-safe without hiding what it was."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    if hasattr(v, "to_dict"):
        return _plain(v.to_dict())
    if hasattr(v, "value") and hasattr(v, "name"):   # Enum
        return v.value
    return str(v)
