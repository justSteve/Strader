"""TPO (Market Profile) entities — time rotated onto the price axis. [st-3zh]

Data only (market/entities convention): the session's half-hour brackets and
which price rows each visited. The time-based sibling of ``VolumeProfile`` —
where that answers "how many contracts traded here", this answers "how many
half-hours accepted this price" (Dalton lineage; foundation doc 03).

Built and interpreted by ``market/orderflow/tpo.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class TPOBracket:
    """One half-hour letter period."""
    letter: str                     # "A", "B", ... in session order
    start_ts: datetime              # first trade in the bracket, US/Central
    end_ts: datetime                # last trade in the bracket
    row_indices: tuple[int, ...]    # ascending indices into TPOProfile.prices
    close: float                    # last traded price of the bracket


@dataclass(frozen=True)
class TPOProfile:
    symbol: str
    session_date: date
    row_pts: float                  # price width of one row (ticks × 0.25)
    prices: tuple[float, ...]       # ascending row floors, contiguous
    brackets: tuple[TPOBracket, ...]  # chronological

    def __post_init__(self) -> None:
        if list(self.prices) != sorted(self.prices):
            raise ValueError("prices must ascend")
        for b in self.brackets:
            if any(i < 0 or i >= len(self.prices) for i in b.row_indices):
                raise ValueError(f"bracket {b.letter} row index out of range")

    def counts(self, upto: int | None = None) -> tuple[int, ...]:
        """TPO count per row (letters printed there), using brackets[:upto].
        ``upto=None`` = full session; ``upto=k`` = developing state after the
        k-th bracket — the drill's mid-flight read."""
        out = [0] * len(self.prices)
        for b in self.brackets[:upto]:
            for i in b.row_indices:
                out[i] += 1
        return tuple(out)

    @property
    def total_tpos(self) -> int:
        return sum(self.counts())
