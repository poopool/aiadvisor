# AI Advisor Bot — Abstract Data Provider (A-FIX-08)
# MarketDataProvider interface; no hardcoded polygon in core logic.
# A-FIX-16: Polygon get_quote implemented (last trade + previous close fallback).
# Phase 12: Tradier provider (A-FIX-18, A-FIX-19), Polygon Analyst gap fill (A-FIX-20), Greeks (A-FIX-21).

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import requests

from app.services.technical_indicators import bars_to_latest


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


class TradierMarketDataProvider(MarketDataProvider):
    """A-FIX-18, A-FIX-19: Tradier implementation. Watchman (quotes) + Analyst (history, chains)."""

    _BASE = "https://api.tradier.com/v1"

    def __init__(self, api_token: str):
        self._token = api_token
        self._headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}

    def get_quote(
        self,
        ticker: str,
        *,
        strike: float | None = None,
        expiry_date: str | None = None,
        strategy: str | None = None,
    ) -> tuple[Decimal, Decimal]:
        """A-FIX-18: (underlying_price, option_mark). GET /markets/quotes; mark from last or (bid+ask)/2."""
        sym = ticker.upper()
        symbols = [sym]
        if strike is not None and expiry_date and strategy:
            symbols.append(_build_tradier_option_symbol(sym, expiry_date, strategy, strike))
        try:
            r = requests.get(
                f"{self._BASE}/markets/quotes",
                params={"symbols": ",".join(symbols)},
                headers=self._headers,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            quotes = data.get("quotes", {}).get("quote")
            if not quotes:
                raise NotImplementedError(f"Tradier: no quote for {sym}")
            if not isinstance(quotes, list):
                quotes = [quotes]
            by_symbol = {q.get("symbol", ""): q for q in quotes if q.get("symbol")}
            underlying_q = by_symbol.get(sym)
            if not underlying_q:
                raise NotImplementedError(f"Tradier: no underlying quote for {sym}")
            underlying_price = underlying_q.get("last") or underlying_q.get("bid") or underlying_q.get("ask") or 0
            underlying_price = Decimal(str(underlying_price))

            if len(symbols) == 1:
                return underlying_price, Decimal("0")

            opt_sym = symbols[1]
            opt_q = by_symbol.get(opt_sym)
            if not opt_q:
                raise NotImplementedError(f"Tradier: no option quote for {opt_sym}")
            last = opt_q.get("last")
            bid = opt_q.get("bid")
            ask = opt_q.get("ask")
            if last is not None:
                option_mark = Decimal(str(last))
            elif bid is not None and ask is not None:
                option_mark = (Decimal(str(bid)) + Decimal(str(ask))) / 2
            elif bid is not None:
                option_mark = Decimal(str(bid))
            elif ask is not None:
                option_mark = Decimal(str(ask))
            else:
                raise NotImplementedError(f"Tradier: no mark for option {opt_sym}")
            return underlying_price, option_mark
        except requests.RequestException as e:
            raise NotImplementedError(f"Tradier quote failed: {e}") from e

    def get_daily_bars(self, ticker: str) -> dict[str, Any]:
        """A-FIX-19: GET /markets/history; compute latest (close, sma_50, sma_200, atr_14, rsi_14)."""
        end = date.today()
        start = end - timedelta(days=400)
        try:
            r = requests.get(
                f"{self._BASE}/markets/history",
                params={"symbol": ticker.upper(), "interval": "daily", "start": start.isoformat(), "end": end.isoformat()},
                headers=self._headers,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            history = data.get("history")
            if not history:
                raise NotImplementedError(f"Tradier: no history for {ticker}")
            days = history.get("day") if isinstance(history.get("day"), list) else ([history.get("day")] if history.get("day") else [])
            bars = []
            for d in days:
                if not isinstance(d, dict):
                    continue
                bars.append({
                    "date": d.get("date"),
                    "open": d.get("open"),
                    "high": d.get("high"),
                    "low": d.get("low"),
                    "close": d.get("close"),
                    "volume": d.get("volume"),
                })
            if not bars:
                raise NotImplementedError(f"Tradier: empty history for {ticker}")
            latest = bars_to_latest(bars, default_iv_30d=Decimal("0.25"))
            return {"ticker": ticker.upper(), "bars": bars, "latest": latest}
        except requests.RequestException as e:
            raise NotImplementedError(f"Tradier history failed: {e}") from e

    def get_option_chain(self, ticker: str) -> dict[str, Any]:
        """A-FIX-19: GET /markets/options/expirations then /markets/options/chains per expiry; map to puts (30-45 DTE)."""
        today = date.today()
        dte_min, dte_max = 30, 45
        min_d = today + timedelta(days=dte_min)
        max_d = today + timedelta(days=dte_max)
        try:
            r = requests.get(
                f"{self._BASE}/markets/options/expirations",
                params={"symbol": ticker.upper()},
                headers=self._headers,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            expirations = data.get("expirations", {}).get("date")
            if not expirations:
                return {"ticker": ticker.upper(), "expirations": [], "puts": [], "calls": []}
            if not isinstance(expirations, list):
                expirations = [expirations]
            target_dates = []
            for ex in expirations:
                if not ex:
                    continue
                d = ex if isinstance(ex, date) else date.fromisoformat(str(ex).split("T")[0])
                if min_d <= d <= max_d:
                    target_dates.append(d.isoformat())
            puts = []
            calls = []
            for exp_str in sorted(target_dates):
                r2 = requests.get(
                    f"{self._BASE}/markets/options/chains",
                    params={"symbol": ticker.upper(), "expiration": exp_str, "greeks": "true"},
                    headers=self._headers,
                    timeout=15,
                )
                r2.raise_for_status()
                chain_data = r2.json()
                opts = chain_data.get("options", {}).get("option")
                if not opts:
                    continue
                if not isinstance(opts, list):
                    opts = [opts]
                for o in opts:
                    strike_f = float(o.get("strike", 0))
                    bid = float(o.get("bid") or 0)
                    ask = float(o.get("ask") or 0)
                    g = o.get("greeks") or {}
                    delta = float(g.get("delta") or 0)
                    iv = float(g.get("mid_iv") or g.get("ask_iv") or g.get("bid_iv") or 0)
                    row = {"strike": strike_f, "expiry": exp_str, "delta": delta, "bid": bid, "ask": ask, "iv": iv}
                    if (o.get("option_type") or "").lower() == "put":
                        row["delta"] = -abs(delta) if delta else 0
                        puts.append(row)
                    else:
                        calls.append(row)
            return {"ticker": ticker.upper(), "expirations": sorted(target_dates), "puts": puts, "calls": calls}
        except requests.RequestException as e:
            raise NotImplementedError(f"Tradier option chain failed: {e}") from e

    def get_greeks_for_position(
        self, ticker: str, strike: float, expiry_date: str, strategy: str
    ) -> dict[str, float] | None:
        """A-FIX-21: Parse greeks from Tradier quote (delta, theta, gamma)."""
        opt_sym = _build_tradier_option_symbol(ticker.upper(), expiry_date, strategy, strike)
        try:
            r = requests.get(
                f"{self._BASE}/markets/quotes",
                params={"symbols": opt_sym},
                headers=self._headers,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            quotes = data.get("quotes", {}).get("quote")
            if not quotes:
                return None
            q = quotes[0] if isinstance(quotes, list) else quotes
            g = q.get("greeks")
            if not g:
                return None
            return {
                "delta": float(g.get("delta", 0)),
                "theta": float(g.get("theta", 0)),
                "gamma": float(g.get("gamma", 0)),
            }
        except (requests.RequestException, KeyError, TypeError, ValueError):
            return None


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


def _build_tradier_option_symbol(underlying: str, expiry_date: str, strategy: str, strike: float) -> str:
    """Build Tradier (OCC) option symbol: AAPL260320P00160000 (underlying + YYMMDD + C/P + 8-digit strike)."""
    parts = expiry_date.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid expiry_date for Tradier symbol: {expiry_date!r}")
    y, m, d = parts[0], parts[1], parts[2]
    yy = y[-2:] if len(y) >= 2 else y
    date_part = f"{yy}{m}{d}"
    right = "C" if strategy and "CALL" in strategy.upper() else "P"
    # OCC strike: 8 digits, strike * 1000 (e.g. 160.0 -> 160000 -> 00160000)
    strike_cents = int(round(float(strike) * 1000))
    strike_part = str(strike_cents).zfill(8)
    return f"{underlying.upper()}{date_part}{right}{strike_part}"


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
        except (requests.RequestException, KeyError, TypeError, ValueError):
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
        except (requests.RequestException, KeyError, TypeError, ValueError):
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
        """A-FIX-20: GET /v2/aggs/ticker/.../range/1/day; compute latest (close, sma_50, sma_200, atr_14, rsi_14)."""
        end = date.today()
        start = end - timedelta(days=400)
        url = f"{self._BASE}/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        try:
            r = requests.get(url, params={"apiKey": self._api_key, "limit": 50000}, timeout=15)
            r.raise_for_status()
            data = r.json()
            results = data.get("results") or []
            if not results:
                raise NotImplementedError(f"Polygon: no daily bars for {ticker}")
            bars = []
            for b in results:
                t_ms = b.get("t")
                if t_ms:
                    dt = datetime.fromtimestamp(t_ms / 1000.0, tz=timezone.utc).date()
                    bar_date = dt.isoformat()
                else:
                    bar_date = None
                bars.append({
                    "date": bar_date,
                    "t": t_ms,
                    "o": b.get("o"),
                    "h": b.get("h"),
                    "l": b.get("l"),
                    "c": b.get("c"),
                })
            latest = bars_to_latest(bars, default_iv_30d=Decimal("0.25"))
            return {"ticker": ticker.upper(), "bars": bars, "latest": latest}
        except requests.RequestException as e:
            raise NotImplementedError(f"Polygon get_daily_bars failed: {e}") from e

    def get_option_chain(self, ticker: str) -> dict[str, Any]:
        """A-FIX-20: GET /v3/snapshot/options/{underlying}; filter 30-45 DTE; map to puts/calls (strike, expiry, delta, bid, ask, iv)."""
        today = date.today()
        dte_min, dte_max = 30, 45
        min_d = today + timedelta(days=dte_min)
        max_d = today + timedelta(days=dte_max)
        underlying = ticker.upper()
        url = f"{self._BASE}/v3/snapshot/options/{underlying}"
        try:
            r = requests.get(url, params={"apiKey": self._api_key, "limit": 250}, timeout=15)
            r.raise_for_status()
            data = r.json()
            results = data.get("results") or []
            puts = []
            calls = []
            seen_expirations = set()
            for opt in results:
                exp_str = opt.get("details", {}).get("expiration_date") or opt.get("expiration_date")
                if not exp_str:
                    continue
                d = date.fromisoformat(exp_str.split("T")[0]) if isinstance(exp_str, str) else exp_str
                if not (min_d <= d <= max_d):
                    continue
                seen_expirations.add(exp_str.split("T")[0])
                strike_f = float(opt.get("details", {}).get("strike_price") or opt.get("strike_price") or 0)
                g = opt.get("details", {}).get("greeks") or opt.get("greeks") or {}
                delta = float(g.get("delta") or 0)
                iv = float(g.get("implied_volatility") or g.get("iv") or 0)
                quote = opt.get("last_quote") or opt.get("quote") or {}
                bid = float(quote.get("bid") or opt.get("bid") or 0)
                ask = float(quote.get("ask") or opt.get("ask") or 0)
                row = {"strike": strike_f, "expiry": exp_str.split("T")[0], "delta": delta, "bid": bid, "ask": ask, "iv": iv}
                ctype = (opt.get("details", {}).get("contract_type") or opt.get("contract_type") or "").upper()
                if "PUT" in ctype or (opt.get("right") or "").upper() == "P":
                    row["delta"] = -abs(delta) if delta else 0
                    puts.append(row)
                else:
                    calls.append(row)
            expirations = sorted(seen_expirations)
            return {"ticker": underlying, "expirations": expirations, "puts": puts, "calls": calls}
        except requests.RequestException as e:
            raise NotImplementedError(f"Polygon get_option_chain failed: {e}") from e

    def get_greeks_for_position(
        self, ticker: str, strike: float, expiry_date: str, strategy: str
    ) -> dict[str, float] | None:
        """A-FIX-21: Fetch option chain snapshot filtered by strike/expiry and return normalized {delta, theta, gamma}."""
        exp_ymd = expiry_date.split("T")[0] if expiry_date else ""
        contract_type = "put" if strategy and "PUT" in strategy.upper() else "call"
        url = f"{self._BASE}/v3/snapshot/options/{ticker.upper()}"
        try:
            r = requests.get(
                url,
                params={
                    "apiKey": self._api_key,
                    "expiration_date": exp_ymd,
                    "strike_price": strike,
                    "contract_type": contract_type,
                    "limit": 1,
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("results") or []
            if not results:
                return None
            opt = results[0] if isinstance(results, list) else results
            g = opt.get("details", {}).get("greeks") or opt.get("greeks") or {}
            if not g:
                return None
            delta = float(g.get("delta", 0))
            if contract_type == "put":
                delta = -abs(delta)
            return {
                "delta": delta,
                "theta": float(g.get("theta", 0)),
                "gamma": float(g.get("gamma", 0)),
            }
        except (requests.RequestException, KeyError, TypeError, ValueError):
            return None


def get_market_data_provider(
    mock: bool | None = None,
    polygon_api_key: str | None = None,
    data_provider: str | None = None,
    tradier_api_token: str | None = None,
) -> MarketDataProvider:
    """A-OPS-09: Factory. mock=True overrides → Mock. Else DATA_PROVIDER TRADIER → Tradier, else Polygon."""
    from app.config import settings
    use_mock = mock if mock is not None else getattr(settings, "ingestion_mock_mode", True)
    if use_mock:
        return MockMarketDataProvider()
    provider_name = (data_provider or getattr(settings, "data_provider", "POLYGON")).upper()
    if provider_name == "TRADIER":
        token = tradier_api_token or getattr(settings, "tradier_api_token", "") or ""
        if not token:
            return MockMarketDataProvider()
        return TradierMarketDataProvider(token)
    api_key = polygon_api_key if polygon_api_key is not None else getattr(settings, "polygon_api_key", "") or ""
    if not api_key:
        return MockMarketDataProvider()
    return PolygonMarketDataProvider(api_key)
