from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Trade(TimestampMixin, Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    strategy: Mapped[str] = mapped_column(String(32))  # BUTTERFLY, VERTICAL, SINGLE
    underlying: Mapped[str] = mapped_column(String(16), default="SPX")
    direction: Mapped[str] = mapped_column(String(8))  # LONG, SHORT
    legs: Mapped[str] = mapped_column(Text)  # JSON array of leg details
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="PENDING"
    )  # PENDING, FILLED, CLOSED, CANCELLED
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class TradeLog(Base):
    __tablename__ = "trade_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_delta: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_gamma: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_theta: Mapped[float] = mapped_column(Float, default=0.0)
    portfolio_vega: Mapped[float] = mapped_column(Float, default=0.0)
