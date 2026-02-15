# AI Advisor Bot — Abstract Data Provider (A-FIX-08)
# MarketDataProvider interface; no hardcoded polygon in core logic.
# A-FIX-16: Polygon get_quote implemented (last trade + previous close fallback).

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any

import requests


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

    def get_quote(
        self,
        ticker: str,
        *,
        strike: float | None = None,
        expiry_date: str | None = None,
        strategy: str | None = None,
    ) -> tuple[Decimal, Decimal]:
        """(underlying_price, option_mark). Option context (strike, expiry_date, strategy) required for real option mark."""
        raise NotImplementedError("Quote not implemented for this provider.")

    def get_greeks_for_position(
        self, ticker: str, strike: float, expiry_date: str, strategy: str
    ) -> dict[str, float] | None:
        """A-P11-02: Live Delta, Theta, Gamma for an active position. Returns e.g. {delta, theta, gamma} or None."""
        ...


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

    def get_quote(
        self,
        ticker: str,
        *,
        strike: float | None = None,
        expiry_date: str | None = None,
        strategy: str | None = None,
    ) -> tuple[Decimal, Decimal]:
        """A-P2-02: (underlying_price, option_mark) for Watchman mark/price polling. Ignores option args."""
        return Decimal("175.50"), Decimal("3.40")

    def get_greeks_for_position(
        self, ticker: str, strike: float, expiry_date: str, strategy: str
    ) -> dict[str, float] | None:
        """A-P11-02: Live Greeks for Watchman. Mock returns sample values."""
        return {"delta": -0.21, "theta": 0.05, "gamma": 0.02}


def _build_polygon_option_ticker(underlying: str, expiry_date: str, strategy: str, strike: float) -> str:
    """Build Polygon option ticker: O:AAPL260320C00150000 (O: + underlying + YYMMDD + C/P + 8-digit strike)."""
    # expiry_date like "2026-03-20" -> 260320
    parts = expiry_date.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid expiry_date for option ticker: {expiry_date!r}")
    y, m, d = parts[0], parts[1], parts[2]
    yy = y[-2:] if len(y) >= 2 else y
    date_part = f"{yy}{m}{d}"
    # C for call, P for put
    right = "C" if strategy and "CALL" in strategy.upper() else "P"
    # Strike in cents, zero-padded to 8 digits (e.g. 150.0 -> 150000 -> 00150000)
    strike_cents = int(round(float(strike) * 1000))
    strike_part = str(strike_cents).zfill(8)
    return f"O:{underlying.upper()}{date_part}{right}{strike_part}"


class PolygonMarketDataProvider(MarketDataProvider):
    """Polygon.io implementation; requires POLYGON_API_KEY. A-FIX-16: get_quote implemented."""

    _BASE = "https://api.polygon.io"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def _get_last_trade(self, ticker: str) -> float | None:
        """Return last trade price or None. Works for stocks and options (O:...)."""
        url = f"{self._BASE}/v2/last/trade/{ticker}"
        try:
            r = requests.get(url, params={"apiKey": self._api_key}, timeout=10)
            r.raise_for_status()
            data = r.json()
            res = data.get("results") or data.get("result")
            if res is not None and isinstance(res, dict) and "p" in res:
                return float(res["p"])
            return None
        except (requests.RequestException, (KeyError, TypeError, ValueError)):
            return None

    def _get_previous_close(self, ticker: str) -> float | None:
        """Return previous session close price. Works for stocks and options. results is an array."""
        url = f"{self._BASE}/v2/aggs/ticker/{ticker}/prev"
        try:
            r = requests.get(url, params={"apiKey": self._api_key}, timeout=10)
            r.raise_for_status()
            data = r.json()
            res = data.get("results")
            if isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict) and "c" in res[0]:
                return float(res[0]["c"])
            if isinstance(res, dict) and "c" in res:
                return float(res["c"])
            return None
        except (requests.RequestException, (KeyError, TypeError, ValueError)):
            return None

    def get_quote(
        self,
        ticker: str,
        *,
        strike: float | None = None,
        expiry_date: str | None = None,
        strategy: str | None = None,
    ) -> tuple[Decimal, Decimal]:
        """A-FIX-16: (underlying_price, option_mark). Last trade; fallback to previous close if no trade today."""
        underlying = ticker.upper()
        # Underlying: last trade then previous close fallback
        underlying_price = self._get_last_trade(underlying)
        if underlying_price is None:
            underlying_price = self._get_previous_close(underlying)
        if underlying_price is None:
            raise NotImplementedError(
                f"Polygon: no last trade or previous close for underlying {underlying}"
            )

        if strike is None or not expiry_date or not strategy:
            # No option context: return underlying only; option_mark as zero (caller may not use)
            return Decimal(str(underlying_price)), Decimal("0")

        option_ticker = _build_polygon_option_ticker(underlying, expiry_date, strategy, strike)
        option_mark = self._get_last_trade(option_ticker)
        if option_mark is None:
            option_mark = self._get_previous_close(option_ticker)
        if option_mark is None:
            raise NotImplementedError(
                f"Polygon: no last trade or previous close for option {option_ticker}"
            )

        return Decimal(str(underlying_price)), Decimal(str(option_mark))

    def get_daily_bars(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError("Polygon get_daily_bars not implemented. Use MockMarketDataProvider.")

    def get_option_chain(self, ticker: str) -> dict[str, Any]:
        raise NotImplementedError("Polygon get_option_chain not implemented. Use MockMarketDataProvider.")

    def get_greeks_for_position(
        self, ticker: str, strike: float, expiry_date: str, strategy: str
    ) -> dict[str, float] | None:
        raise NotImplementedError("Polygon get_greeks_for_position not implemented. Use MockMarketDataProvider.")


def get_market_data_provider(mock: bool = True, polygon_api_key: str = "") -> MarketDataProvider:
    """Factory: returns Mock or Polygon provider based on config."""
    if mock or not polygon_api_key:
        return MockMarketDataProvider()
    return PolygonMarketDataProvider(polygon_api_key)
