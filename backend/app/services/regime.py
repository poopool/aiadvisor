# AI Advisor Bot — Market Regime Filter (A-P1-07)
# No Short Put if SPY is below 200-day SMA.

from decimal import Decimal
from typing import Any

from app.services.ingestion import fetch_market_data


def check_spy_above_sma200(*, mock: bool = True) -> tuple[bool, str, Decimal | None]:
    """
    Returns (allows_short_put, regime_label, spy_close).
    allows_short_put is False when SPY is below 200-day SMA.
    """
    data = fetch_market_data("SPY", mock=mock)
    latest = data["latest"]
    close = latest["close"]
    sma_200 = latest.get("sma_200")
    if sma_200 is None:
        return True, "UNKNOWN_SPY", close
    if close >= sma_200:
        return True, "BULLISH_SPY_OVER_200SMA", close
    return False, "BEARISH_SPY_BELOW_200SMA", close
