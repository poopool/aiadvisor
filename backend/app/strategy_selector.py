# AI Advisor Bot — Strategy Selector (A-P1-04)
# Maps technical state to option strategy. §4 Trend/RSI states.

from decimal import Decimal
from typing import Literal

# Trend: Bullish = Price > SMA_200 and Price > SMA_50; Bearish = Price < SMA_50
# RSI: Overbought > 70, Oversold < 30


def get_trend_state(
    price: Decimal,
    sma_50: Decimal | None,
    sma_200: Decimal | None,
) -> Literal["bullish", "bearish", "neutral"]:
    if sma_200 is not None and sma_50 is not None:
        if price > sma_200 and price > sma_50:
            return "bullish"
        if price < sma_50:
            return "bearish"
    return "neutral"


def get_rsi_state(rsi_14: Decimal) -> Literal["overbought", "oversold", "neutral"]:
    if rsi_14 > Decimal("70"):
        return "overbought"
    if rsi_14 < Decimal("30"):
        return "oversold"
    return "neutral"


def select_strategy(
    trend: Literal["bullish", "bearish", "neutral"],
    rsi_state: Literal["overbought", "oversold", "neutral"],
    regime_allows_short_put: bool,
) -> Literal["SHORT_PUT", "SHORT_CALL", "NONE"]:
    """
    A-P1-04: Map technical state to option strategy.
    Market Regime Filter (A-P1-07): Short Put only when regime_allows_short_put (SPY above 200 SMA).
    """
    if trend == "bearish":
        return "SHORT_CALL"  # or skip; we allow SHORT_CALL
    if trend == "bullish" and rsi_state != "overbought" and regime_allows_short_put:
        return "SHORT_PUT"
    if trend == "neutral" and regime_allows_short_put and rsi_state == "oversold":
        return "SHORT_PUT"
    if trend == "bearish" and rsi_state == "overbought":
        return "SHORT_CALL"
    if regime_allows_short_put and rsi_state == "oversold":
        return "SHORT_PUT"
    return "NONE"
