# AI Advisor Bot — SQLAlchemy Models (Phase 0)
# Source of Truth: PROJECT_CONTEXT.md §6

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class MarketData(Base):
    """
    Cached daily market data for trend/volatility analysis.
    Timeframe: Daily (canonical for SMA, ATR, RSI).
    """

    __tablename__ = "market_data"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    sma_50: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    sma_200: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    atr_14: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=True)
    rsi_14: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=True)
    iv_30d: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)  # as decimal e.g. 0.25
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    def __repr__(self) -> str:
        return f"MarketData(ticker={self.ticker!r}, date={self.date!r}, close={self.close})"


class TradeRecommendation(Base):
    """
    Phase 1 output: a single trade recommendation (Trades).
    Persisted for audit and frontend Approval Queue.
    """

    __tablename__ = "trade_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. SHORT_PUT
    strike: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")  # PENDING, APPROVED, REJECTED
    calculated_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # §6.1
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    def __repr__(self) -> str:
        return f"TradeRecommendation(id={self.id}, ticker={self.ticker!r}, strategy={self.strategy!r})"


class ActivePosition(Base):
    """
    Watchman state: active position after human approval (§6.2).
    A-FIX-07: Rolling lineage — parent/root/roll_count/realized_pnl_pre_roll for rolls.
    """

    __tablename__ = "active_positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    lifecycle_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="MONITORING")
    entry_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    risk_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    last_heartbeat: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # A-FIX-07: Rolling lineage
    parent_position_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    root_position_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    roll_count: Mapped[int] = mapped_column(default=0)  # 0 = opening trade, 1+ = rolled
    realized_pnl_pre_roll: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    def __repr__(self) -> str:
        return f"ActivePosition(id={self.id}, ticker={self.ticker!r}, stage={self.lifecycle_stage!r})"


class AlertLog(Base):
    """A-P2-07: Alert idempotency — track ALERT_SENT per trigger per position."""

    __tablename__ = "alert_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)  # 21_DTE, STRIKE_TOUCH, STOP_LOSS, TAKE_PROFIT, DATA_STALE
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
