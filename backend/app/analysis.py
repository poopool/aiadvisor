# AI Advisor Bot — Analysis Pipeline (Phase 1)
# A-P1-01 ingestion → A-P1-07 regime → A-P1-04 strategy → A-P1-03/05 chain/strike → A-P1-08 expected move → A-P1-06 thesis

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.quant_engine import QuantLaws
from app.strategy_selector import get_trend_state, get_rsi_state, select_strategy
from app.services.ingestion import fetch_market_data
from app.services.regime import check_spy_above_sma200
from app.services.options import fetch_option_chain, select_strike_by_delta
from app.services.llm_synthesis import synthesize_thesis
from app.services.universe import hard_earnings_exclusion

DEFAULT_DTE_MIN, DEFAULT_DTE_MAX = 30, 45


def run_analysis(ticker: str, *, mock_ingestion: bool = True, use_llm: bool = False) -> dict[str, Any]:
    """
    Full pipeline. Returns Trade Recommendation schema (§6.1).
    Uses SMA_50/SMA_200 for trend, SPY for regime, chain for strike/delta/credit.
    """
    data = fetch_market_data(ticker, mock=mock_ingestion)
    latest = data["latest"]
    price = latest["close"]
    sma_50 = latest.get("sma_50")
    sma_200 = latest.get("sma_200")
    atr_14 = latest["atr_14"]
    rsi_14 = latest["rsi_14"]
    iv_30d = latest["iv_30d"]

    # A-P1-07 Market Regime
    allows_short_put, regime, _ = check_spy_above_sma200(mock=mock_ingestion)

    # Trend & RSI (§4)
    trend = get_trend_state(price, sma_50, sma_200)
    rsi_state = get_rsi_state(rsi_14)

    # A-P1-08 Expected move for target DTE
    dte = (DEFAULT_DTE_MIN + DEFAULT_DTE_MAX) // 2
    expected_move_1sd = QuantLaws.calculate_expected_move(price, iv_30d, dte)
    iv_natr_ratio, efficiency_passes = QuantLaws.check_iv_natr_rule(iv_30d, atr_14, price)
    dte_status = QuantLaws.check_21_dte(dte)

    # A-P1-04 Strategy (A-P1-07: no Short Put when SPY below 200 SMA)
    strategy = select_strategy(trend, rsi_state, allows_short_put)
    # A-FIX-04: Ticker-level trend filter — block Short Put if Ticker_Price < Ticker_SMA_50
    if strategy == "SHORT_PUT" and sma_50 is not None and price < sma_50:
        strategy = "NONE"
    if strategy == "NONE":
        strategy = "SHORT_CALL"  # or skip; avoid Short Put when regime blocks

    # A-P1-03 / A-P1-05 Option chain and strike selection
    chain = fetch_option_chain(ticker, mock=mock_ingestion)
    selected = select_strike_by_delta(chain, (0.20, 0.30))

    if selected:
        strike = Decimal(str(selected["strike"]))
        expiry_str = selected["expiry"]
        expiry_date = date.fromisoformat(expiry_str)
        delta = float(selected.get("delta", -0.20))
        credit_est = (float(selected.get("bid", 0)) + float(selected.get("ask", 0))) / 2
        contract = f"{ticker.upper()}{expiry_date.strftime('%y%m%d')}P{int(strike * 1000):08d}"
    else:
        strike = (price - expected_move_1sd).quantize(Decimal("0.01"))
        if strike <= 0:
            strike = price * Decimal("0.90")
        expiry_date = date.today() + timedelta(days=dte)
        strike = strike.quantize(Decimal("0.01"))
        delta = -0.20
        credit_est = 3.50
        contract = f"{ticker.upper()}{expiry_date.strftime('%y%m%d')}P{int(strike * 1000):08d}"

    # A-FIX-03: Hard Earnings Exclusion — NO_TRADE if earnings between Today and Expiry
    earnings_date = latest.get("earnings_date")  # date or None
    if hard_earnings_exclusion(earnings_date, expiry_date):
        now = datetime.now(timezone.utc)
        return {
            "ticker": ticker.upper(),
            "timestamp": now.isoformat().replace("+00:00", "Z"),
            "regime": regime,
            "no_trade": True,
            "reason": "NO_TRADE: Earnings event between today and expiry.",
            "analysis": {"price": float(price), "rsi_14": float(rsi_14), "trend": trend, "earnings_date": earnings_date.isoformat() if hasattr(earnings_date, "isoformat") else earnings_date},
            "recommendation": None,
        }

    # Safety: strike outside 1-SD
    safety_ok = strike < (price - expected_move_1sd)
    safety_check = "Strike is outside 1-SD expected move" if safety_ok else "Strike within 1-SD; review manually"

    analysis_payload = {
        "price": float(price),
        "rsi_14": float(rsi_14),
        "trend": trend,
        "iv_rank": 65,
        "iv_natr_ratio": float(iv_natr_ratio),
        "expected_move_1sd": float(expected_move_1sd),
        "earnings_date": None,
    }

    recommendation_payload = {
        "strategy": strategy,
        "contract": contract,
        "strike": float(strike),
        "expiry": expiry_date.isoformat(),
        "delta": delta,
        "credit_est": round(credit_est, 2),
        "safety_check": safety_check,
        "thesis": synthesize_thesis(ticker, analysis_payload, recommendation_payload, use_llm=use_llm),
    }

    now = datetime.now(timezone.utc)
    return {
        "ticker": ticker.upper(),
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "regime": regime,
        "analysis": analysis_payload,
        "recommendation": recommendation_payload,
    }
