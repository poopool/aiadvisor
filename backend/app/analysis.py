# AI Advisor Bot — Analysis Pipeline (Phase 1)
# A-P1-01 ingestion → A-P1-07 regime → A-P1-04 strategy → Efficiency Gate → contract (if not NONE) → thesis

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


def run_analysis(
    ticker: str,
    *,
    mock_ingestion: bool = True,
    use_llm: bool = False,
    market_data_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Full pipeline. Returns Trade Recommendation schema (§6.1).
    Uses SMA_50/SMA_200 for trend, SPY for regime, chain for strike/delta/credit.
    Efficiency Gate: SHORT_PUT only if IV/NATR > 1.0; otherwise strategy = NONE.
    When market_data_result is provided (e.g. after fetch + persist), uses it instead of fetching.
    """
    data = market_data_result if market_data_result is not None else fetch_market_data(ticker, mock=mock_ingestion)
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

    # 1) Calculate metrics: expected move, IV/NATR ratio, efficiency gate (Ratio > 1.0)
    dte = (DEFAULT_DTE_MIN + DEFAULT_DTE_MAX) // 2
    expected_move_1sd = QuantLaws.calculate_expected_move(price, iv_30d, dte)
    iv_natr_ratio, efficiency_passes = QuantLaws.check_iv_natr_rule(iv_30d, atr_14, price)
    dte_status = QuantLaws.check_21_dte(dte)

    analysis_payload = {
        "price": float(price),
        "rsi_14": float(rsi_14),
        "trend": trend,
        "iv_rank": 65,
        "iv_natr_ratio": float(iv_natr_ratio),
        "expected_move_1sd": float(expected_move_1sd),
        "earnings_date": None,
    }

    # A-P1-04 Strategy (A-P1-07: no Short Put when SPY below 200 SMA)
    strategy = select_strategy(trend, rsi_state, allows_short_put)
    # A-FIX-04: Ticker-level trend filter — block Short Put if Ticker_Price < Ticker_SMA_50
    if strategy == "SHORT_PUT" and sma_50 is not None and price < sma_50:
        strategy = "NONE"
    # 2) Apply Efficiency Gate: IV/NATR > 1.0 required for Short Put; otherwise NONE
    if strategy == "SHORT_PUT" and not efficiency_passes:
        strategy = "NONE"

    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")

    # 3) Select contract only if strategy is valid (not NONE)
    if strategy == "NONE":
        recommendation_payload = {
            "strategy": "NONE",
            "thesis": "Vol check failed: IV/NATR ratio not above 1.0.",
        }
        return {
            "ticker": ticker.upper(),
            "timestamp": timestamp,
            "regime": regime,
            "analysis": analysis_payload,
            "recommendation": recommendation_payload,
        }

    # Strategy is SHORT_PUT or SHORT_CALL — fetch chain and select strike
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
    earnings_date = latest.get("earnings_date")
    if hard_earnings_exclusion(earnings_date, expiry_date):
        return {
            "ticker": ticker.upper(),
            "timestamp": timestamp,
            "regime": regime,
            "no_trade": True,
            "reason": "NO_TRADE: Earnings event between today and expiry.",
            "analysis": {**analysis_payload, "earnings_date": earnings_date.isoformat() if hasattr(earnings_date, "isoformat") else earnings_date},
            "recommendation": None,
        }

    safety_ok = strike < (price - expected_move_1sd)
    safety_check = "Strike is outside 1-SD expected move" if safety_ok else "Strike within 1-SD; review manually"

    recommendation_payload = {
        "strategy": strategy,
        "contract": contract,
        "strike": float(strike),
        "expiry": expiry_date.isoformat(),
        "delta": delta,
        "credit_est": round(credit_est, 2),
        "safety_check": safety_check,
    }

    # 4) Thesis generation at the very end
    recommendation_payload["thesis"] = synthesize_thesis(
        ticker,
        analysis_payload,
        recommendation_payload,
        use_llm=use_llm,
    )

    return {
        "ticker": ticker.upper(),
        "timestamp": timestamp,
        "regime": regime,
        "analysis": analysis_payload,
        "recommendation": recommendation_payload,
    }
