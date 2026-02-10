# AI Advisor Bot — Option Chain Fetcher (A-P1-03) & Strike Selection (A-P1-05)
# A-FIX-08: Uses MarketDataProvider interface; no hardcoded polygon in core.

from typing import Any


def fetch_option_chain(ticker: str, *, mock: bool = True, provider=None) -> dict[str, Any]:
    """
    A-P1-03: Fetch option chain via MarketDataProvider. Filter for 30–45 DTE in implementation.
    Returns { "expirations": [...], "puts": [ { "strike", "expiry", "delta", "bid", "ask", "iv" }, ... ] }.
    """
    if provider is None:
        from app.config import settings
        from app.services.providers import get_market_data_provider
        provider = get_market_data_provider(mock=mock, polygon_api_key=settings.polygon_api_key)
    return provider.get_option_chain(ticker)


# A-FIX-02: Option liquidity gate — (Ask - Bid) / Bid_Price < 0.10 (Spread < 10%)
OPTION_SPREAD_MAX_PCT = 0.10


def filter_puts_by_liquidity(puts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A-FIX-02: Keep only puts where (Ask - Bid) / Bid_Price < 0.10."""
    out = []
    for p in puts:
        bid = float(p.get("bid") or 0)
        ask = float(p.get("ask") or 0)
        if bid <= 0:
            continue
        spread_pct = (ask - bid) / bid
        if spread_pct < OPTION_SPREAD_MAX_PCT:
            out.append(p)
    return out


def select_strike_by_delta(
    chain: dict[str, Any],
    target_delta_range: tuple[float, float] = (0.20, 0.30),
) -> dict[str, Any] | None:
    """
    A-P1-05: Select put strike by delta (short put: negative delta ~0.20–0.30).
    A-FIX-02: Only considers puts passing option spread gate (Ask-Bid)/Bid < 10%.
    """
    puts = chain.get("puts") or []
    puts = filter_puts_by_liquidity(puts)
    low, high = target_delta_range
    in_range = [p for p in puts if low <= abs(float(p.get("delta", 0))) <= high]
    if not in_range:
        return None
    return min(in_range, key=lambda p: abs(abs(float(p["delta"])) - (low + high) / 2))
