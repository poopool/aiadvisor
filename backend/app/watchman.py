# AI Advisor Bot — Watchman (Phase 2)
# A-P2-02 Poller, A-P2-03 21 DTE, A-P2-04 Strike touch, A-P2-05 Stop loss, A-P2-06 Take profit, A-P2-07 Idempotency, A-P2-08 Heartbeat
# A-OPS-08: Debug logging (logger.debug for cycle flow)

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

logger = logging.getLogger("watchman")
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ActivePosition, AlertLog
# Mark price source: mock or from ingestion; > 60 min old → DATA_STALE
# A-P5-02: DATA_STALE_MINUTES could be from config; A-FIX-11: no silent fallback — raise DataFetchError


class DataFetchError(Exception):
    """A-FIX-11: Raised when mark/quote cannot be fetched (e.g. provider not implemented). No fake data."""


ALERT_CRITICAL_DATA_STALE = "CRITICAL_DATA_STALE"


def _data_stale_minutes() -> int:
    from app.config import settings
    return getattr(settings, "data_stale_minutes", 60) or 60


async def get_mark_price_for_position(
    ticker: str,
    *,
    entry_data: dict | None = None,
    mock: bool = True,
) -> tuple[Decimal, Decimal, datetime]:
    """
    Return (mark_price, underlying_price, fetched_at). A-P2-02 / A-P2-04: Smart Polling for Watchman.
    A-FIX-11: Raises DataFetchError if quote not available. A-FIX-16: entry_data passed for Polygon option quote.
    """
    now = datetime.now(timezone.utc)
    if mock:
        return Decimal("3.40"), Decimal("175.50"), now
    from app.config import settings
    from app.services.providers import get_market_data_provider
    provider = get_market_data_provider(mock=False)
    try:
        ed = entry_data or {}
        strike = ed.get("short_strike")
        expiry_date = ed.get("expiry_date")
        strategy = ed.get("strategy")
        quote = provider.get_quote(
            ticker, strike=strike, expiry_date=expiry_date, strategy=strategy
        )
        # Providers may return either (underlying, option) or (underlying, option, quote_timestamp).
        if len(quote) == 3:
            underlying_price, option_mark, quote_timestamp = quote
        else:
            underlying_price, option_mark = quote
            quote_timestamp = now
        return option_mark, underlying_price, quote_timestamp
    except NotImplementedError as e:
        raise DataFetchError(f"Quote not implemented for provider (ticker={ticker})") from e


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
        logger.debug("Checking ticker %s (position_id=%s)", pos.ticker, str(pos.id))
        try:
            mark, underlying_price, fetched_at = await get_mark_price_for_position(
                pos.ticker, entry_data=pos.entry_data or {}, mock=mock
            )
        except DataFetchError as e:
            # A-FIX-11: Skip this position, do not use fake data; continue with others.
            logger.warning("Skipping %s due to quote fetch failure: %s", pos.ticker, e)
            continue
        entry = pos.entry_data or {}
        risk = pos.risk_rules or {}
        strike = Decimal(str(entry.get("short_strike", 0)))
        entry_price = Decimal(str(entry.get("entry_price", 0)))
        expiry_date_str = entry.get("expiry_date")
        expiry_date = date.fromisoformat(expiry_date_str) if expiry_date_str else date.today()

        strategy = entry.get("strategy")

        # Update last_heartbeat
        data_fresh = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60 <= _data_stale_minutes()
        pos.last_heartbeat = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "mark_timestamp": fetched_at.isoformat().replace("+00:00", "Z"),
            "mark_price": float(mark),
            "underlying_price": float(underlying_price),
            "data_freshness_status": "OK" if data_fresh else "STALE",
        }
        logger.debug("Price updated for %s: mark=%s underlying=%s", pos.ticker, mark, underlying_price)

        # A-P11-01: P&L engine — market_value, unrealized_pnl, return_pct (Short: profit when Entry > Mark)
        contracts = int(entry.get("contracts", 1))
        mult = Decimal(100) * contracts
        pos.market_value = mark * mult
        # Short position: unrealized P&L = (Entry - Mark) * 100 * Contracts
        pos.unrealized_pnl = (entry_price - mark) * mult
        credit_received = entry_price * mult
        pos.return_pct = (pos.unrealized_pnl / credit_received * 100) if credit_received else None

        # A-P11-02: Live Greeks ingestion during Watchman cycle
        try:
            from app.config import settings
            from app.services.providers import get_market_data_provider
            provider = get_market_data_provider(mock=mock)
            greeks = provider.get_greeks_for_position(
                pos.ticker, float(strike), expiry_date_str or "", strategy or ""
            )
            if greeks is not None:
                pos.greeks = greeks
        except (NotImplementedError, Exception):
            pass  # leave pos.greeks unchanged if provider does not support or errors

        # A-P2-04 Strike Touch: underlying price crosses the short strike
        if strategy == "SHORT_PUT" and underlying_price <= strike:
            if await _ensure_alert_sent(db, pos.id, "STRIKE_TOUCH"):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "STRIKE_TOUCH"})
            pos.lifecycle_stage = "CLOSING_URGENT"
        elif strategy == "SHORT_CALL" and underlying_price >= strike:
            if await _ensure_alert_sent(db, pos.id, "STRIKE_TOUCH"):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "STRIKE_TOUCH"})
            pos.lifecycle_stage = "CLOSING_URGENT"

        # A-P2-03 21 DTE (threshold from config via QuantLaws)
        dte = (expiry_date - date.today()).days
        from app.quant_engine import _get_dte_alert_threshold
        if dte <= _get_dte_alert_threshold():
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
            pos.lifecycle_stage = "CLOSING_URGENT"

        # A-P5-04: Income Shield (Roll Logic) — ROLL_NEEDED if (Price-Strike)/Strike > roll_itm_pct AND DTE < roll_dte_trigger
        from app.config import settings
        roll_itm_pct = Decimal(str(getattr(settings, "roll_itm_pct", 0.03)))
        roll_dte_trigger = getattr(settings, "roll_dte_trigger", 14)
        if strategy == "SHORT_PUT" and strike and strike > 0 and underlying_price < strike:
            itm_ratio = (strike - underlying_price) / strike
            if itm_ratio >= roll_itm_pct and dte < roll_dte_trigger:
                if await _ensure_alert_sent(db, pos.id, "ROLL_NEEDED"):
                    triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "ROLL_NEEDED"})

        # A-P2-07 Data freshness
        if not data_fresh:
            if await _ensure_alert_sent(db, pos.id, ALERT_CRITICAL_DATA_STALE):
                triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": ALERT_CRITICAL_DATA_STALE})

        # Close positions automatically at force_close_date once they reached the forced date.
        force_close_date_str = risk.get("force_close_date")
        if force_close_date_str:
            force_close_date = date.fromisoformat(force_close_date_str)
            if date.today() >= force_close_date and pos.lifecycle_stage != "CLOSED":
                pos.lifecycle_stage = "CLOSED"
                pos.status = "CLOSED"
                if await _ensure_alert_sent(db, pos.id, "FORCE_CLOSED"):
                    triggered.append({"position_id": str(pos.id), "ticker": pos.ticker, "trigger": "FORCE_CLOSED"})

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
