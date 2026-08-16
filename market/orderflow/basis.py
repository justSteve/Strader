"""Live SPX→ES basis from the 1 Hz vendor spot. [st-n0qm.8]

Everything GexBot publishes is SPX-domain; the footprint is ES. Nothing in the
live stack maintained the conversion, so ``touch``/``dflip`` in
``gex_context`` compared mixed units and every sentinel row would have landed
~20 points off the chart. This is the one estimate that turns an SPX strike
into an ES price on the page: ``es ≈ spx + basis``.

Source: ``gexbot_orderflow_1s.jsonl`` — one row a second, vendor ``timestamp``
(epoch s) and ``spot``. Measured 2026-08-16 (``scripts/measurement/
basis_pairs.py``): on 08-14 the vendor spot against the ES print in the same
vendor second gives median +20.75 with a p95 absolute deviation of 0.70 pt
across RTH, agreeing with the three Schwab in-session snapshots (+20.21 …
+20.89). Fresh to the second, so it is a usable live source and rows need no
error band. The rows the sentinel skips (vendor-stale prior-close snapshot,
zeroed reset) are skipped here too — same shapes, same reasons.

Estimate: per closed bar, pair the bar's close with the vendor row at or
before ``bar.end_ts`` and no older than ``max_pair_age_s``; the sample is
``close − spot``; the estimate is the median of the last ``window`` samples.
A median over ten volume bars rides the intra-day drift (~0.5 pt over a
session, carry decaying) and shrugs off one odd second. Never raises: a basis
that cannot be estimated is reported as ``None`` and the page says so.
"""
from __future__ import annotations

import json
import logging
import statistics
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("strader.orderflow.basis")

WINDOW = 10               # samples in the median
MAX_PAIR_AGE_S = 5.0      # vendor row may be this much older than the bar close
STALE_ROW_S = 120.0       # vendor `timestamp` this far behind ts_pull_utc: a
                          # prior-session snapshot, not a market row (sentinel rule)
TRIM_BEHIND_S = 600.0     # rows older than the last sampled bar by this are dropped


def _f(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def row_spot(row: dict) -> tuple[float, float] | None:
    """(vendor epoch seconds, spot) for a usable market row, else None.

    Refuses: collector-marked anomalies; the zeroed reset (both major-gamma
    levels equal and aggregate DEX exactly 0); a vendor timestamp more than
    STALE_ROW_S behind the pull time; a non-positive or missing spot.
    """
    if not isinstance(row, dict) or "anomaly" in row:
        return None
    ts, spot = _f(row.get("timestamp")), _f(row.get("spot"))
    if ts is None or spot is None or spot <= 0:
        return None
    ml, ms = row.get("z_mlgamma"), row.get("z_msgamma")
    if ml is not None and ml == ms and row.get("agg_dex") == 0:
        return None
    pull = row.get("ts_pull_utc")
    if isinstance(pull, str):
        try:
            p = datetime.fromisoformat(pull.replace("Z", "+00:00"))
            if p.tzinfo is None:
                p = p.replace(tzinfo=timezone.utc)
            if p.timestamp() - ts > STALE_ROW_S:
                return None
        except ValueError:
            pass
    return ts, spot


class BasisEstimator:
    """Incremental reader over a day's 1 Hz file plus the rolling median."""

    def __init__(self, path: Path | str, *, window: int = WINDOW,
                 max_pair_age_s: float = MAX_PAIR_AGE_S):
        self.path = Path(path)
        self.window = int(window)
        self.max_pair_age_s = float(max_pair_age_s)
        self._offset = 0
        self._rows: list[tuple[float, float]] = []      # ascending (ts, spot)
        self._samples: deque[float] = deque(maxlen=self.window)
        self._last_pair_age: float | None = None
        self._last_sample_ts: float | None = None

    # -- ingest -----------------------------------------------------------

    def refresh(self) -> int:
        """Consume newly appended rows. Returns how many usable rows were added.
        Never raises; a torn final line is left for the next call."""
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
                        self._offset = pos
                        break
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    pair = row_spot(row)
                    if pair is None:
                        continue
                    if self._rows and pair[0] < self._rows[-1][0]:
                        continue            # out-of-order vendor second: drop
                    self._rows.append(pair)
                    added += 1
                return added
        except OSError as e:
            logger.warning("basis: could not read %s (%s)", self.path, e)
            return 0

    # -- estimate ---------------------------------------------------------

    def spot_at(self, when: datetime) -> tuple[float, float] | None:
        """(age_s, spot) of the newest vendor row at or before ``when`` and no
        older than max_pair_age_s; None otherwise. At-or-before, never after —
        the same no-lookahead rule GexContext.poll_at keeps."""
        if when is None or not self._rows:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        t = when.timestamp()
        # rows are ascending; scan from the end (the match is almost always last)
        for ts, spot in reversed(self._rows):
            if ts <= t:
                age = t - ts
                return (age, spot) if age <= self.max_pair_age_s else None
        return None

    def sample(self, bar) -> dict:
        """Add the sample for one CLOSED bar (if a fresh vendor row pairs with
        it) and return the current estimate. Never raises."""
        try:
            end = getattr(bar, "end_ts", None)
            close = _f(getattr(bar, "close", None))
            hit = self.spot_at(end) if close is not None else None
            if hit is not None:
                age, spot = hit
                self._samples.append(round(close - spot, 2))
                self._last_pair_age = round(age, 1)
                self._last_sample_ts = end.timestamp()
            # Memory stays flat over a day by trimming BEHIND the bar just
            # sampled, never at refresh: bars arrive in time order, so a row
            # older than the last bar by ten minutes can never pair again —
            # and a whole-file refresh followed by an offline replay (the
            # hindsight harness) sees exactly the rows the live loop saw.
            if end is not None and len(self._rows) > 2000:
                cut = end.timestamp() - TRIM_BEHIND_S
                k = 0
                while k < len(self._rows) and self._rows[k][0] < cut:
                    k += 1
                if k:
                    del self._rows[:k]
        except Exception as e:  # noqa: BLE001 — a render nicety never kills the feed
            logger.warning("basis: sample failed (%s: %s)", type(e).__name__, e)
        return self.estimate()

    def estimate(self, now: datetime | None = None) -> dict:
        """{pts, n, age_s} — pts None until the first sample; age_s is how old
        the newest sample is (None when unknown)."""
        if not self._samples:
            return {"pts": None, "n": 0, "age_s": None}
        age = None
        if self._last_sample_ts is not None:
            ref = (now or datetime.now(timezone.utc))
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            age = round(ref.timestamp() - self._last_sample_ts, 1)
        return {"pts": round(statistics.median(self._samples), 2),
                "n": len(self._samples), "age_s": age}
