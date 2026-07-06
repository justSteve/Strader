"""Volume profile entity — traded volume rotated onto the price axis.

Data only (market/entities convention): one completed window's per-price
volume histogram. Built by ``market/orderflow/profile.py``; interpreted into
Level signals there. The Dalton/Market-Profile lineage: POC is the most-
accepted price, LVNs are prices the market rejected and moved through fast
(research doc Q1.6).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VolumeProfile:
    symbol: str
    start_ts: datetime            # first trade in the window, US/Central
    end_ts: datetime              # last trade in the window
    bucket_pts: float             # price width of one bucket (ticks × 0.25)
    prices: tuple[float, ...]     # ascending bucket floors, contiguous
    volumes: tuple[int, ...]      # contracts per bucket, parallel to prices

    def __post_init__(self) -> None:
        if len(self.prices) != len(self.volumes):
            raise ValueError("prices and volumes must be parallel")
        if list(self.prices) != sorted(self.prices):
            raise ValueError("prices must ascend")

    @property
    def total(self) -> int:
        return sum(self.volumes)

    @property
    def poc_price(self) -> float:
        """Point of control — highest-volume bucket; lower price wins ties
        (same convention as FootprintBar.poc_price)."""
        best = max(range(len(self.volumes)), key=lambda i: (self.volumes[i], -self.prices[i]))
        return self.prices[best]
