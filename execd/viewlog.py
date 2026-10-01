"""The view log — what Steve's screen showed, one JSON line per change. [st-6pfc]

Desk's work order (2026-10-01, Steve: "yes, my words"): Desk cannot see the
tailnet pages, so it reads a file. Every order-page render or poll whose
DISPLAYED values changed writes one line to ``<dir>/YYYY-MM-DD.jsonl``
(``/var/moo/surface/execd`` for the Schwab instance) — the values the page
was sent, taken from the same objects the page and the poll payload are
built from, never recomputed afterwards.

The cost is kept off the request path:

* **Change detection at display precision.** The request thread formats the
  record's displayed values the way the page shows them (prices to the cent,
  deltas to 0.01, the words of an error) and hashes that tuple; an unchanged
  hash for the same page and viewer is dropped there and then. Raw floats
  are never compared, so jitter below what the screen shows writes nothing.
* **Enqueue only.** A changed record goes on a bounded queue that drops its
  oldest entry when full and counts the drop. The request never blocks,
  never writes, never raises.
* **One writer thread** coalesces each page+viewer to at most one line a
  second, keeping the latest state, appends to the day's open file, flushes
  every ~2 s, rolls the file at the CT date and prunes files older than 14
  days at its start and at each roll. A write error is swallowed and
  counted; the counts are in the service's ``/status`` (``view_log``).
* **Runners-up** — the strikes the chooser passed over and why — are worked
  out in the writer, from the chain the chooser already read, and only on a
  line where the chosen strike or the delta cap changed; other lines carry
  the chosen strike's numbers alone.

Left out of every line: account numbers, tokens, the passphrase, and the
broker's order ids. Buying power goes in as a figure — it changes which
strike is chosen.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .bounds import CT

log = logging.getLogger("execd.viewlog")

DEFAULT_VIEW_LOG_DIR = Path("/var/moo/surface/execd")
RETAIN_DAYS = 14
QUEUE_MAX = 2000
COALESCE_S = 1.0
FLUSH_S = 2.0
TICK_S = 0.25
RUNNERS_UP_MAX = 12

#: keys a line may never carry, at any depth (st-6pfc; tests/execd/
#: test_viewlog.py asserts none ever appears)
EXCLUDED_KEYS = frozenset({"order_id", "stop_order_id", "target_order_id", "exit_order_id",
                           "account", "account_number", "account_hash", "accountNumber",
                           "hashValue", "token", "access_token", "refresh_token", "passphrase",
                           "credential", "secret"})


def viewer_tag(user_agent: str | None) -> str:
    """``ipad-3f9a1c`` / ``phone-…`` / ``desktop-…``: the device kind from the
    User-Agent, and a short hash of it so two desktops differ. iPadOS
    Safari calls itself a Macintosh, but says ``Mobile`` in its WebKit
    token; a Mac does not."""
    ua = user_agent or ""
    if "iPad" in ua or ("Macintosh" in ua and "Mobile" in ua):
        kind = "ipad"
    elif "iPhone" in ua or "Android" in ua or "Mobile" in ua:
        kind = "phone"
    else:
        kind = "desktop"
    return f"{kind}-{hashlib.sha1(ua.encode('utf-8', 'replace')).hexdigest()[:6]}"


def _c(v: Any) -> str:
    """A price as the page shows it: to the cent."""
    return "" if v is None else f"{float(v):.2f}"


def _d(v: Any) -> str:
    return "" if v is None else f"{abs(float(v)):.2f}"


def _contract(c: Any) -> dict[str, Any]:
    return {"strike": c.strike, "delta": round(abs(c.delta), 2), "bid": round(c.bid_pts, 2),
            "ask": round(c.ask_pts, 2), "spread": round(c.ask_pts - c.bid_pts, 2)}


def order_record(*, sel: Any, priced: Any, st: Mapping[str, Any], sendable: bool | None,
                 closes: list[Mapping[str, Any]] | None = None,
                 today_text: str | None = None) -> tuple[dict[str, Any], tuple]:
    """The order page as sent: the record and its display tuple. Built on
    the request thread from the objects the payload was built from; cheap
    (no chain reads, no runners-up — those are the writer's)."""
    q = sel.as_query() if sel is not None else {}
    query = {k: q.get(k) for k in ("side", "expiry", "delta", "strike", "lots", "stopoff",
                                   "stop", "limit", "exitspx") if q.get(k) is not None}
    if sel is not None and "limit" in query:
        query["padlock"] = True
    # the side on every line, and in the display tuple so a switch is a line
    # (st-n4tr)
    rec: dict[str, Any] = {"page": "order", "mode": st.get("mode"), "query": query}
    disp: list[Any] = [st.get("mode"), tuple(sorted(query.items()))]
    if priced is not None:
        c = priced.contract
        rec["spx"] = round(priced.spx, 2) if priced.spx else None
        rec["cap"] = priced.cap
        rec["buying_power"] = priced.funds
        rec["chosen"] = _contract(c) if c is not None else None
        rec["manual_strike"] = sel.strike is not None
        rec["ticket"] = {"limit": priced.limit, "stop_price": priced.stop_price,
                         "stop_spx": priced.stop_spx, "cost_usd": priced.cost_usd,
                         "error": priced.error, "warnings": list(priced.warnings),
                         "send_enabled": sendable}
        disp += [_c(priced.spx), _d(priced.cap), _c(priced.funds),
                 (c.strike, _d(c.delta), _c(c.bid_pts), _c(c.ask_pts)) if c is not None else None,
                 _c(priced.limit), _c(priced.stop_price), _c(priced.stop_spx),
                 _c(priced.cost_usd), priced.error or "", tuple(priced.warnings), sendable]
    positions = []
    for p in st.get("positions") or []:
        v = p.get("valuation") or {}
        positions.append({
            "symbol": str(p.get("symbol", "")).strip(), "qty": p.get("qty"),
            "entry_price": p.get("entry_price"), "stop_price": p.get("stop_price"),
            "stop_spx": p.get("stop_spx"), "target_price": p.get("target_price"),
            "target_spx": p.get("target_spx"), "bid": v.get("bid"),
            "net_usd": v.get("net_if_closed_usd"), "gross_usd": v.get("gross_if_closed_usd"),
            "stop_state": p.get("stop_state"), "target_state": p.get("target_state"),
            "closing": bool(p.get("exit_order_id"))})
    if positions:
        rec["positions"] = positions
        disp += [tuple((x["symbol"], x["qty"], _c(x["entry_price"]), _c(x["stop_price"]),
                        _c(x["stop_spx"]), _c(x["target_price"]), _c(x["bid"]),
                        _c(x["net_usd"]), x["stop_state"], x["target_state"], x["closing"])
                       for x in positions)]
    working = [{"symbol": str(w.get("symbol", "")).strip(), "qty": w.get("qty"),
                "limit": w.get("limit")} for w in st.get("working") or []]
    if working:
        rec["working"] = working
        disp += [tuple((w["symbol"], w["qty"], _c(w["limit"])) for w in working)]
    if closes:
        rec["closed"] = [{"symbol": str(c.get("symbol", "")).strip(), "qty": c.get("qty"),
                          "entry_price": c.get("entry_price"), "exit_price": c.get("exit_price"),
                          "pnl_usd": c.get("pnl_usd"), "net_usd": c.get("net_usd"),
                          "reason": c.get("kind") or c.get("reason")} for c in closes]
        disp += [tuple((x["symbol"], _c(x["exit_price"]), _c(x["pnl_usd"]), x["reason"])
                       for x in rec["closed"])]
    if today_text:
        rec["today"] = today_text
        disp.append(today_text)
    return rec, tuple(disp)


class ViewLog:
    """The queue, the writer and the day's file. ``enabled=False`` (the
    ``--no-view-log`` flag) makes :meth:`offer` a no-op."""

    def __init__(self, directory: str | Path | None = DEFAULT_VIEW_LOG_DIR, *,
                 enabled: bool = True, clock: Callable[[], datetime] | None = None,
                 retain_days: int = RETAIN_DAYS, queue_max: int = QUEUE_MAX,
                 coalesce_s: float = COALESCE_S, flush_s: float = FLUSH_S,
                 start: bool = True) -> None:
        self.dir = Path(directory) if directory else None
        self.enabled = bool(enabled and self.dir is not None)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.retain_days = retain_days
        self.coalesce_s = coalesce_s
        self.flush_s = flush_s
        self._q: deque[tuple[str, dict[str, Any], Any]] = deque()
        self._qmax = queue_max
        self._qlock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        #: request side: the last display hash offered, per page+viewer
        self._last_hash: dict[str, str] = {}
        #: writer side
        self._latest: dict[str, tuple[dict[str, Any], Any]] = {}
        self._written_at: dict[str, float] = {}
        self._last_choice: dict[str, tuple] = {}
        self._fh: Any = None
        self._day: date | None = None
        self._last_flush = 0.0
        self.counts = {"offered": 0, "unchanged": 0, "queued": 0, "dropped": 0,
                       "lines": 0, "bytes": 0, "write_errors": 0, "pruned": 0}
        self._thread: threading.Thread | None = None
        if self.enabled and start:
            self.start()

    # ── the request side ────────────────────────────────────────────────
    def offer(self, viewer: str, record: dict[str, Any], display: tuple,
              priced: Any = None) -> None:
        """Hand a page's record to the log. Never blocks, never raises."""
        if not self.enabled:
            return
        try:
            key = f"{record.get('page', '?')}|{viewer}"
            h = hashlib.blake2b(repr(display).encode("utf-8", "replace"), digest_size=8).hexdigest()
            self.counts["offered"] += 1
            if self._last_hash.get(key) == h:
                self.counts["unchanged"] += 1
                return
            self._last_hash[key] = h
            now = self.clock()
            record = {"ts_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
                      "ts_ct": now.astimezone(CT).strftime("%Y-%m-%d %H:%M:%S"),
                      "viewer": viewer, **record}
            with self._qlock:
                if len(self._q) >= self._qmax:
                    self._q.popleft()
                    self.counts["dropped"] += 1
                self._q.append((key, record, priced))
                self.counts["queued"] += 1
            self._wake.set()
        except Exception:  # noqa: BLE001 — logging must never fail a poll
            self.counts["write_errors"] += 1

    def health(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "dir": str(self.dir) if self.dir else None,
                "writer_alive": bool(self._thread and self._thread.is_alive()),
                **dict(self.counts)}

    # ── the writer ──────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="execd-viewlog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.drain(force=True)
        self._close()

    def _run(self) -> None:
        self.prune()
        while not self._stop.is_set():
            self._wake.wait(TICK_S)
            self._wake.clear()
            try:
                self.drain()
            except Exception:  # noqa: BLE001 — the writer never dies
                self.counts["write_errors"] += 1
                log.exception("view log: the writer pass failed")

    def drain(self, *, force: bool = False, now_s: float | None = None) -> int:
        """One writer pass: take the queue, keep the latest per page+viewer,
        write each whose last line is ``coalesce_s`` old (or all, ``force``),
        flush when due. Returns the lines written. Called by the thread; a
        test may call it directly with ``start=False``."""
        import time
        with self._qlock:
            items = list(self._q)
            self._q.clear()
        for key, rec, priced in items:
            self._latest[key] = (rec, priced)
        t = time.monotonic() if now_s is None else now_s
        wrote = 0
        for key in list(self._latest):
            if not force and t - self._written_at.get(key, -1e9) < self.coalesce_s:
                continue
            rec, priced = self._latest.pop(key)
            self._add_runners_up(key, rec, priced)
            if self._write(rec):
                wrote += 1
            self._written_at[key] = t
        if self._fh is not None and (force or t - self._last_flush >= self.flush_s):
            try:
                self._fh.flush()
            except OSError:
                self.counts["write_errors"] += 1
            self._last_flush = t
        return wrote

    def _add_runners_up(self, key: str, rec: dict[str, Any], priced: Any) -> None:
        chosen = rec.get("chosen")
        choice = (chosen.get("strike") if chosen else None, rec.get("cap"),
                  (rec.get("query") or {}).get("side"))
        if self._last_choice.get(key) == choice or priced is None:
            self._last_choice[key] = choice
            return
        self._last_choice[key] = choice
        prev = rec.setdefault("decision", {})
        prev["changed"] = True
        try:
            from .orderform import DEFAULT_STOP_PTS, why_not
            sel = priced.selection
            lots = max(1, sel.lots)
            off = sel.stopoff if sel.stopoff is not None else DEFAULT_STOP_PTS
            cap = priced.cap if priced.cap is not None else 0.8
            chosen_sym = priced.contract.symbol if priced.contract is not None else None
            rows = []
            for c in sorted(priced.chain, key=lambda c: abs(c.delta or 0), reverse=True):
                if c.symbol == chosen_sym:
                    continue
                why = why_not(c, cap=cap, funds=priced.funds, lots=lots, off=off)
                rows.append({**_contract(c), "lost": why or "lower delta than the chosen"})
            # the ones that matter: around the chosen strike by delta
            if chosen is not None:
                rows.sort(key=lambda r: abs(r["delta"] - chosen["delta"]))
            prev["runners_up"] = rows[:RUNNERS_UP_MAX]
            prev["reason"] = ("the strike he set" if sel.strike is not None else
                              f"highest delta at or under {cap:g} that is a legal order")
        except Exception:  # noqa: BLE001 — a line without runners-up is still a line
            self.counts["write_errors"] += 1

    def _write(self, rec: dict[str, Any]) -> bool:
        try:
            day = datetime.fromisoformat(rec["ts_utc"]).astimezone(CT).date()
            if day != self._day:
                self._roll(day)
            line = json.dumps(_scrub(rec), separators=(",", ":"), default=str) + "\n"
            self._fh.write(line)
            self.counts["lines"] += 1
            self.counts["bytes"] += len(line.encode("utf-8"))
            return True
        except Exception:  # noqa: BLE001 — swallowed and counted
            self.counts["write_errors"] += 1
            return False

    def _roll(self, day: date) -> None:
        self._close()
        assert self.dir is not None
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{day.isoformat()}.jsonl"
        self._fh = path.open("a", encoding="utf-8")
        try:
            os.chmod(path, 0o644)         # Desk reads it; the service's umask is 0077
        except OSError:
            pass
        self._day = day
        self.prune(today=day)

    def _close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except OSError:
                self.counts["write_errors"] += 1
            self._fh = None

    def prune(self, today: date | None = None) -> int:
        """Delete day files older than ``retain_days``."""
        if self.dir is None or not self.dir.is_dir():
            return 0
        today = today or self.clock().astimezone(CT).date()
        cutoff = today - timedelta(days=self.retain_days)
        n = 0
        for f in self.dir.glob("????-??-??.jsonl"):
            try:
                if date.fromisoformat(f.stem) < cutoff:
                    f.unlink()
                    n += 1
            except (ValueError, OSError):
                continue
        self.counts["pruned"] += n
        return n


def _scrub(v: Any) -> Any:
    """The excluded keys out, at any depth — a backstop: the record is built
    from a whitelist and never asks for them."""
    if isinstance(v, dict):
        return {k: _scrub(x) for k, x in v.items() if k not in EXCLUDED_KEYS}
    if isinstance(v, list):
        return [_scrub(x) for x in v]
    return v
