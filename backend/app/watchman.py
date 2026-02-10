# AI Advisor Bot — Watchman (Phase 2)
# A-P2-02 Poller, A-P2-03 21 DTE, A-P2-04 Strike touch, A-P2-05 Stop loss, A-P2-06 Take profit, A-P2-07 Idempotency, A-P2-08 Heartbeat

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ActivePosition, AlertLog
from app.quant_engine import QuantLaws


# Mark price source: mock or from ingestion; > 60 min old → DATA_STALE
DATA_STALE_MINUTES = 60


async def get_mark_price_for_position(ticker: str, *, mock: bool = True) -> tuple[Decimal, Decimal, datetime]:
    """Return (mark_price, underlying_price, fetched_at). A-P2-04 Strike Touch uses underlying_price."""
    if mock:
        return Decimal("3.40"), Decimal("175.50"), datetime.now(timezone.utc)
    # TODO: fetch from Polygon option quote + stock quote
    return Decimal("3.40"), Decimal("175.50"), datetime.now(timezone.utc)


async def run_watchman_cycle(db: AsyncSession, *, mock: bool = True) -> list[dict[str, Any]]:
    """
    One Watchman cycle: load open positions, update mark, check rules, log alerts (idempotent).
    Returns list of triggered alert summaries.
    """
    result = await db.execute(
        select(ActivePosition).where(ActivePosition.lifecycle_stage != "CLOSED").order_by(ActivePosition.created_at.desc())
    )
    positions = result.scalars().all()
    triggered: list[dict[str, Any]] = []

    for pos in positions:
        mark, underlying_price, fetched_at = await get_mark_price_for_position(pos.ticker, mock=mock)
        entry = pos.entry_data or {}
        risk = pos.risk_rules or {}
        strike = Decimal(str(entry.get("short_strike", 0)))
        entry_price = Decimal(str(entry.get("entry_price", 0)))
        expiry_date_str = entry.get("expiry_date")
        expiry_date = date.fromisoformat(expiry_date_str) if expiry_date_str else date.today()

        # Update last_heartbeat
        data_fresh = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60 <= DATA_STALE_MINUTES
        pos.last_heartbeat = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "mark_price": float(mark),
            "underlying_price": float(underlying_price),
            "data_freshness_status": "OK" if data_fresh else "STALE",
        }

        # A-P2-04 Strike Touch: underlying <= short strike
        if underlying_price <= strike:
            if await _ensure_alert_sent(db, pos.id, "STRIKE_TOUCH"):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "STRIKE_TOUCH"})
            pos.lifecycle_stage = "CLOSING_URGENT"

        # A-P2-03 21 DTE
        dte = (expiry_date - date.today()).days
        if dte <= QuantLaws.DTE_ALERT_THRESHOLD:
            if await _ensure_alert_sent(db, pos.id, "21_DTE"):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "21_DTE"})
            pos.lifecycle_stage = "CLOSING_URGENT"

        # A-P2-05 Stop loss: Mark >= 3 * entry
        stop_loss_price = Decimal(str(risk.get("stop_loss_price", 0)))
        if stop_loss_price and mark >= stop_loss_price:
            if await _ensure_alert_sent(db, pos.id, "STOP_LOSS"):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "STOP_LOSS"})
            pos.lifecycle_stage = "CLOSING_URGENT"

        # A-P2-06 Take profit: Mark <= 0.5 * entry
        take_profit_price = Decimal(str(risk.get("take_profit_price", 0)))
        if take_profit_price and mark <= take_profit_price:
            if await _ensure_alert_sent(db, pos.id, "TAKE_PROFIT"):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "TAKE_PROFIT"})

        # A-P2-07 Data freshness
        if not data_fresh:
            if await _ensure_alert_sent(db, pos.id, "DATA_STALE"):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "CRITICAL_DATA_STALE"})

    await db.flush()
    return triggered


async def _ensure_alert_sent(db: AsyncSession, position_id: UUID, trigger_type: str) -> bool:
    """A-P2-07: Return True if we should send (first time); creates log and returns False on duplicate."""
    existing = await db.execute(
        select(AlertLog).where(AlertLog.position_id == position_id, AlertLog.trigger_type == trigger_type)
    )
    if existing.scalar_one_or_none():
        return False
    log = AlertLog(position_id=position_id, trigger_type=trigger_type, sent_at=datetime.now(timezone.utc))
    db.add(log)
    await db.flush()
    return True


def get_heartbeat_message() -> dict[str, Any]:
    """A-P2-08: System Online heartbeat (call every 4h)."""
    return {
        "type": "SYSTEM_ONLINE",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "message": "Watchman system online.",
    }
