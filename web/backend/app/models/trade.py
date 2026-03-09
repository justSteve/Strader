from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Text, DateTime, Date, JSON
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    trade_id = Column(String(64), unique=True, nullable=False)
    symbol = Column(String(32), nullable=False, default="SPX")
    strategy = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=False)
    legs = Column(JSON, nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Numeric(12, 2), nullable=False)
    exit_price = Column(Numeric(12, 2))
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True))
    pnl = Column(Numeric(12, 2))
    fees = Column(Numeric(8, 2), default=0)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    account_hash = Column(String(128), nullable=False)
    symbol = Column(String(32), nullable=False)
    option_symbol = Column(String(64))
    quantity = Column(Integer, nullable=False)
    avg_price = Column(Numeric(12, 2), nullable=False)
    current_price = Column(Numeric(12, 2))
    market_value = Column(Numeric(14, 2))
    delta = Column(Numeric(8, 4))
    gamma = Column(Numeric(8, 6))
    theta = Column(Numeric(8, 4))
    vega = Column(Numeric(8, 4))
    pnl_day = Column(Numeric(12, 2))
    pnl_total = Column(Numeric(12, 2))
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class DailyPnL(Base):
    __tablename__ = "daily_pnl"

    id = Column(Integer, primary_key=True)
    trade_date = Column(Date, unique=True, nullable=False)
    realized_pnl = Column(Numeric(12, 2), default=0)
    unrealized_pnl = Column(Numeric(12, 2), default=0)
    fees = Column(Numeric(8, 2), default=0)
    trade_count = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    max_drawdown = Column(Numeric(12, 2), default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    alert_type = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False, default="info")
    message = Column(Text, nullable=False)
    data = Column(JSON)
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class RiskLimit(Base):
    __tablename__ = "risk_limits"

    id = Column(Integer, primary_key=True)
    limit_name = Column(String(64), unique=True, nullable=False)
    limit_value = Column(Numeric(14, 2), nullable=False)
    current_value = Column(Numeric(14, 2), default=0)
    breached = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
