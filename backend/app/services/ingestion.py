# AI Advisor Bot — Ingestion Service (Phase 1)
# A-P1-01: Input list of tickers → Output JSON with Price, SMA_50, RSI_14, ATR_14, IV_30d. Daily only.
# A-FIX-08: Uses MarketDataProvider interface; no hardcoded polygon in core.

from typing import Any


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
        from decimal import Decimal
        latest = out["latest"]
        for k in ("close", "sma_50", "sma_200", "atr_14", "rsi_14", "iv_30d"):
            if k in latest and latest[k] is not None and not isinstance(latest[k], Decimal):
                latest[k] = Decimal(str(latest[k]))
    return out


def fetch_market_data_batch(tickers: list[str], *, mock: bool = True) -> list[dict[str, Any]]:
    """A-P1-01: Input list of tickers. Output list of JSON with Price, SMA_50, RSI_14, ATR_14, IV_30d."""
    return [fetch_market_data(t, mock=mock) for t in tickers]
