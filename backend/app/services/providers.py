# AI Advisor Bot — Abstract Data Provider (A-FIX-08)
# MarketDataProvider interface; no hardcoded polygon in core logic.

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any


class MarketDataProvider(ABC):
    """A-FIX-08: Abstract provider for market and option data. Implementations: Mock, Polygon, etc."""

    @abstractmethod
    def get_daily_bars(self, ticker: str) -> dict[str, Any]:
        """Return { ticker, bars: [...], latest: { close, sma_50, sma_200, atr_14, rsi_14, iv_30d, ... } }."""
        ...

    @abstractmethod
    def get_option_chain(self, ticker: str) -> dict[str, Any]:
        """Return { ticker, expirations: [...], puts: [ { strike, expiry, delta, bid, ask, iv }, ... ] }."""
        ...

    def get_quote(self, ticker: str) -> tuple[Decimal, Decimal]:
        """Optional: (underlying_price, option_mark) for a ticker. Default: raise NotImplementedError."""
        raise NotImplementedError("Quote not implemented for this provider.")


class MockMarketDataProvider(MarketDataProvider):
    """Mock provider for testing; no external API calls."""

    def get_daily_bars(self, ticker: str) -> dict[str, Any]:
        from datetime import timedelta
        today = date.today()
        close = Decimal("175.50")
        sma_50 = Decimal("172.00")
        sma_200 = Decimal("165.00")
        return {
            "ticker": ticker.upper(),
            "bars": [],
            "latest": {
                "date": today.isoformat(),
                "close": close,
                "sma_50": sma_50,
                "sma_200": sma_200,
                "atr_14": Decimal("4.20"),
                "rsi_14": Decimal("28.5"),
                "iv_30d": Decimal("0.24"),  # 24% — realistic; Efficiency Gate (IV/NATR > 1.0) will filter in normal dev
            },
        }

    def get_option_chain(self, ticker: str) -> dict[str, Any]:
        from datetime import timedelta
        expiry = date.today() + timedelta(days=35)
        return {
            "ticker": ticker.upper(),
            "expirations": [expiry.isoformat()],
            "puts": [
                {"strike": 160.0, "expiry": expiry.isoformat(), "delta": -0.30, "bid": 3.80, "ask": 4.00, "iv": 0.34},
                {"strike": 155.0, "expiry": expiry.isoformat(), "delta": -0.22, "bid": 2.90, "ask": 3.10, "iv": 0.33},
                {"strike": 150.0, "expiry": expiry.isoformat(), "delta": -0.18, "bid": 2.10, "ask": 2.30, "iv": 0.32},
            ],
        }

    def get_quote(self, ticker: str) -> tuple[Decimal, Decimal]:
        """A-P2-02: (underlying_price, option_mark) for Watchman mark/price polling."""
        return Decimal("175.50"), Decimal("3.40")


class PolygonMarketDataProvider(MarketDataProvider):
    """Polygon.io implementation; requires POLYGON_API_KEY. No hardcoded calls in core — all via this interface."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def get_daily_bars(self, ticker: str) -> dict[str, Any]:
        # from polygon import RESTClient; client = RESTClient(self._api_key); ...
        raise NotImplementedError("Polygon get_daily_bars not implemented. Use MockMarketDataProvider.")

    def get_option_chain(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError("Polygon get_option_chain not implemented. Use MockMarketDataProvider.")


def get_market_data_provider(mock: bool = True, polygon_api_key: str = "") -> MarketDataProvider:
    """Factory: returns Mock or Polygon provider based on config."""
    if mock or not polygon_api_key:
        return MockMarketDataProvider()
    return PolygonMarketDataProvider(polygon_api_key)
