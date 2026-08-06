"""Gamma context for a footprint bar — what dealers were positioned for. [st-8ywx]

THE POINT. The footprint says what *happened* at a price. GEX says what *should*
have happened there. Neither is worth much alone at a level: heavy volume with no
price progress is dealers mechanically absorbing when they are long gamma, and a
real buyer fighting the flow when they are short it. Same cells, same delta,
opposite meaning. Stamping each closed bar with the dealer positioning that was
live when it printed is what lets those two cases ever be told apart.

Stage 1 of the GEX integration deliberately changes NO recognition behaviour. It
joins the two streams and records the join, because the joined dataset is what
makes the later stages (GEX levels as drifting anchors; regime-conditioned
weighting) measurable instead of merely plausible. As of 2026-08-06 there is one
partial session of GEX history — far too little to weight anything by.

DEGRADATION IS THE WHOLE CONTRACT. The GEX feed is RTH-only, polls once a minute,
and lives in a different process that can die on its own. Capture and render must
never care. Every failure here — file absent, unreadable, malformed line, stale
poll, collector down — resolves to ``None`` and a bar that renders exactly as it
does today. There is no code path in this module that can raise into the feeder.

Staleness is REPORTED, never hidden: every context carries ``age_s``, the gap
between the poll and the bar it is attached to. A 40-second-old bracket and a
20-minute-old one are different claims about the market and must not look alike
downstream.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# A poll older than this is not describing the bar in front of you. The feed
# polls at 60s, so 5 minutes tolerates a few missed cycles and still refuses a
# genuinely stale book.
MAX_AGE_S = 300.0


def _f(v) -> float | None:
    """Coerce to float, or None. GexBot nulls fields it has no read for."""
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


class GexContext:
    """Incremental reader over a day's ``gexbot.jsonl``.

    Append-only file, so the read is a resumable tail: hold a byte offset,
    consume whatever is new, keep polls in ascending pull-time order. Cheap
    enough to refresh on every bar close.
    """

    def __init__(self, path: Path | str, *, max_age_s: float = MAX_AGE_S):
        self.path = Path(path)
        self.max_age_s = float(max_age_s)
        self._offset = 0
        self._polls: list[dict] = []

    # -- ingest -----------------------------------------------------------

    def refresh(self) -> int:
        """Consume newly appended polls. Returns how many were added.

        Never raises. A partial final line (the collector mid-write) leaves the
        offset before it so the next refresh re-reads it whole.
        """
        try:
            if not self.path.exists():
                return 0
            with self.path.open("r", encoding="utf-8") as fh:
                fh.seek(self._offset)
                added = 0
                while True:
                    pos = fh.tell()
                    line = fh.readline()
                    if not line:
                        self._offset = pos
                        break
                    if not line.endswith("\n"):
                        # Torn write — rewind and wait for the writer to finish.
                        self._offset = pos
                        break
                    rec = self._parse(line)
                    if rec is not None:
                        self._polls.append(rec)
                        added += 1
                return added
        except OSError as e:
            logger.warning("gex context: could not read %s (%s)", self.path, e)
            return 0

    def _parse(self, line: str) -> dict | None:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict):
            return None
        ts = self._pull_ts(raw.get("ts_pull_utc"))
        if ts is None:
            return None
        s = (raw.get("data") or {}).get("summary") or {}
        resp = (raw.get("data") or {}).get("responses") or {}

        # The classic majors leg carries the flip and the net-GEX sign; the
        # state gamma_zero leg carries the 0DTE bracket. Either may be missing
        # on a cycle that errored — take what is there.
        majors = next((v for k, v in resp.items()
                       if k.endswith("/classic/gex_zero/majors")
                       and isinstance(v, dict) and "zero_gamma" in v), {})

        return {
            "ts": ts,
            "spot": _f(s.get("spot_at_gamma_zero")),
            "flip": _f(majors.get("zero_gamma")),
            "net_gex_oi": _f(majors.get("net_gex_oi")),
            "net_gex_vol": _f(majors.get("net_gex_vol")),
            "pos": _f(s.get("major_positive")),
            "neg": _f(s.get("major_negative")),
            "long_gamma": _f(s.get("major_long_gamma")),
            "short_gamma": _f(s.get("major_short_gamma")),
            "one_pos": _f(s.get("one_major_positive")),
            "one_neg": _f(s.get("one_major_negative")),
        }

    @staticmethod
    def _pull_ts(v) -> datetime | None:
        if not isinstance(v, str):
            return None
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # -- query ------------------------------------------------------------

    def poll_at(self, when: datetime) -> dict | None:
        """The newest poll at or before ``when``, within ``max_age_s``.

        At-or-BEFORE is the point: a bar must never be stamped with positioning
        that had not been published when it printed. That would be lookahead —
        the exact bug ``LiveAnchors`` exists to avoid for range edges — and it
        would silently make every backtest of this data optimistic.
        """
        if when is None or not self._polls:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        best = None
        for rec in self._polls:            # ascending; small (one session)
            if rec["ts"] <= when:
                best = rec
            else:
                break
        if best is None:
            return None
        age = (when - best["ts"]).total_seconds()
        return None if age > self.max_age_s else best

    def for_bar(self, bar) -> dict | None:
        """Gamma context for one closed footprint bar, or None.

        Keys are short because this rides on every bar over the bridge:
          spot/flip/pos/neg  — dealer book at the poll
          regime             — 'pos' | 'neg' | None, from net GEX sign
          dflip              — bar close minus the flip; sign says which side
          touch              — majors the bar's own range covered
          age_s              — how old the poll was when the bar closed
        """
        try:
            rec = self.poll_at(getattr(bar, "end_ts", None))
            if rec is None:
                return None
            close = _f(getattr(bar, "close", None))
            hi, lo = _f(getattr(bar, "high", None)), _f(getattr(bar, "low", None))

            # Sign of net GEX is the regime read: positive = dealers long gamma
            # = hedging dampens moves; negative = hedging amplifies them. OI is
            # preferred over vol as the steadier of the two; vol is the fallback.
            net = rec["net_gex_oi"]
            if net is None:
                net = rec["net_gex_vol"]
            regime = None if net is None else ("pos" if net > 0 else "neg")

            touch = []
            if hi is not None and lo is not None:
                for name in ("pos", "neg", "flip", "long_gamma", "short_gamma"):
                    lvl = rec.get(name)
                    if lvl is not None and lo <= lvl <= hi:
                        touch.append(name)

            dflip = (round(close - rec["flip"], 2)
                     if close is not None and rec["flip"] is not None else None)

            return {
                "ts": rec["ts"].isoformat().replace("+00:00", "Z"),
                "age_s": round((bar.end_ts.astimezone(timezone.utc)
                                - rec["ts"]).total_seconds(), 1),
                "spot": rec["spot"], "flip": rec["flip"],
                "pos": rec["pos"], "neg": rec["neg"],
                "one_pos": rec["one_pos"], "one_neg": rec["one_neg"],
                "regime": regime,
                "net_gex_oi": rec["net_gex_oi"],
                "dflip": dflip,
                "touch": touch,
            }
        except Exception as e:  # a render nicety must never kill capture
            logger.warning("gex context: unusable for bar (%s: %s)",
                           type(e).__name__, e)
            return None
