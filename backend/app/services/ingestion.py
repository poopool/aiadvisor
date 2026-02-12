# AI Advisor Bot — Ingestion Service (Phase 1)
# A-P1-01: Input list of tickers → Output JSON with Price, SMA_50, RSI_14, ATR_14, IV_30d. Daily only.
# §2.2: Persist fetched market data to the Data Layer.

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def fetch_market_data(ticker: str, *, mock: bool = True, provider=None) -> dict[str, Any]:
    """
    Fetch daily market data for a ticker via MarketDataProvider.
    Output includes Price (close), SMA_50, SMA_200, RSI_14, ATR_14, IV_30d.
    """
    if provider is None:
        from app.config import settings
        from app.services.providers import get_market_data_provider
        provider = get_market_data_provider(mock=mock, polygon_api_key=settings.polygon_api_key)
    out = provider.get_daily_bars(ticker)
    # Ensure "latest" has Decimal for core logic
    if "latest" in out and out["latest"]:
        latest = out["latest"]
        for k in ("close", "sma_50", "sma_200", "atr_14", "rsi_14", "iv_30d"):
            if k in latest and latest[k] is not None and not isinstance(latest[k], Decimal):
                latest[k] = Decimal(str(latest[k]))
    return out


def fetch_market_data_batch(tickers: list[str], *, mock: bool = True) -> list[dict[str, Any]]:
    """A-P1-01: Input list of tickers. Output list of JSON with Price, SMA_50, RSI_14, ATR_14, IV_30d."""
    return [fetch_market_data(t, mock=mock) for t in tickers]


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


async def persist_market_data(db: AsyncSession, ticker: str, latest: dict[str, Any]) -> None:
    """
    Persist latest bar to market_data table (§2.2 Data Layer).
    Upserts by (ticker, date). Call after fetch_market_data to satisfy ingestion → Data Layer.
    """
    from database.models import MarketData

    bar_date = latest.get("date")
    if isinstance(bar_date, str):
        bar_date = date.fromisoformat(bar_date)
    if bar_date is None:
        bar_date = date.today()
    ticker = ticker.upper()
    close = _to_decimal(latest.get("close"))
    if close is None:
        return
    result = await db.execute(
        select(MarketData).where(MarketData.ticker == ticker, MarketData.date == bar_date)
    )
    row = result.scalar_one_or_none()
    if row:
        row.close = close
        row.sma_50 = _to_decimal(latest.get("sma_50"))
        row.sma_200 = _to_decimal(latest.get("sma_200"))
        row.atr_14 = _to_decimal(latest.get("atr_14"))
        row.rsi_14 = _to_decimal(latest.get("rsi_14"))
        row.iv_30d = _to_decimal(latest.get("iv_30d"))
    else:
        row = MarketData(
            ticker=ticker,
            date=bar_date,
            close=close,
            sma_50=_to_decimal(latest.get("sma_50")),
            sma_200=_to_decimal(latest.get("sma_200")),
            atr_14=_to_decimal(latest.get("atr_14")),
            rsi_14=_to_decimal(latest.get("rsi_14")),
            iv_30d=_to_decimal(latest.get("iv_30d")),
        )
        db.add(row)
    await db.flush()
