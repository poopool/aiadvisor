# AI Advisor Bot — Analysis Pipeline (Phase 1)
# A-P1-01 ingestion → A-P1-07 regime → A-P1-04 strategy → Efficiency Gate → contract (if not NONE) → thesis

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from app.quant_engine import QuantLaws
from app.strategy_selector import get_trend_state, get_rsi_state, select_strategy
from app.services.ingestion import fetch_market_data
from app.services.regime import check_spy_above_sma200
from app.services.options import fetch_option_chain, select_strike_by_delta, get_skew_25d
from app.services.llm_synthesis import synthesize_thesis
from app.services.universe import hard_earnings_exclusion
from app.watchman import DataFetchError

DEFAULT_DTE_MIN, DEFAULT_DTE_MAX = 30, 45


def run_analysis(
    ticker: str,
    db: Any,
    *,
    mock_ingestion: bool = True,
    use_llm: bool = False,
    market_data_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Full pipeline. Returns Trade Recommendation schema (§6.1).
    Uses SMA_50/SMA_200 for trend, SPY for regime, chain for strike/delta/credit.
    Efficiency Gate: SHORT_PUT only if IV/NATR > 1.5; otherwise strategy = NONE.
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

    # 1) Calculate pre-contract metrics: IV/NATR ratio and efficiency gate
    iv_natr_ratio, efficiency_passes = QuantLaws.check_iv_natr_rule(iv_30d, atr_14, price)

    analysis_payload = {
        "price": float(price),
        "rsi_14": float(rsi_14),
        "trend": trend,
        "iv_natr_ratio": float(iv_natr_ratio),
        # expected_move_1sd and dte_status are added after contract selection (actual DTE required)
        "earnings_date": None,
        "sector": latest.get("sector") or "Unknown",
    }

    # A-P1-04 Strategy (A-P1-07: no Short Put when SPY below 200 SMA)
    strategy = select_strategy(trend, rsi_state, allows_short_put)
    # A-FIX-04: Ticker-level trend filter — block Short Put if Ticker_Price < Ticker_SMA_50
    if strategy == "SHORT_PUT" and sma_50 is not None and price < sma_50:
        strategy = "NONE"
    # 2) Apply Efficiency Gate: IV/NATR > 1.5 required for Short Put; otherwise NONE
    if strategy == "SHORT_PUT" and not efficiency_passes:
        strategy = "NONE"
    # A-P5-03: Refined entry gates — RSI < RSI_ENTRY_THRESHOLD (e.g. 40) for Short Put
    from app.config import settings
    rsi_entry = getattr(settings, "rsi_entry_threshold", 40.0)
    if strategy == "SHORT_PUT" and float(rsi_14) >= rsi_entry:
        strategy = "NONE"

    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")

    # 3) Select contract only if strategy is valid (not NONE)
    if strategy == "NONE":
        recommendation_payload = {
            "strategy": "NONE",
            "thesis": "Vol check failed: IV/NATR ratio not above 1.5.",
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
        delta = Decimal(str(selected.get("delta", -0.20)))
        # A-FIX-12: Use Bid for credit (selling), Ask for buy-to-close cost
        credit_est = Decimal(str(selected.get("bid", 0) or 0))
        buy_to_close_est = Decimal(str(selected.get("ask", 0) or 0))
        # A-P7-01: Use IV at target expiry for efficiency gate (not generic IV_30d)
        iv_target_expiry = float(selected.get("iv", iv_30d))
        iv_target_dec = Decimal(str(iv_target_expiry))
        iv_natr_ratio_target, efficiency_at_expiry = QuantLaws.check_iv_natr_rule(iv_target_dec, atr_14, price)
        if strategy == "SHORT_PUT" and not efficiency_at_expiry:
            return {
                "ticker": ticker.upper(),
                "timestamp": timestamp,
                "regime": regime,
                "analysis": {**analysis_payload, "iv_natr_ratio_at_expiry": float(iv_natr_ratio_target)},
                "recommendation": {"strategy": "NONE", "thesis": "Term structure: IV/NATR at target expiry failed."},
            }
        analysis_payload["iv_natr_ratio_at_expiry"] = float(iv_natr_ratio_target)
        # A-P7-02: Volatility Skew Gate — block Short Put if 25Δ Skew > threshold (points)
        skew_points = get_skew_25d(chain, expiry_str)
        max_skew = getattr(settings, "max_skew_threshold", 10.0)
        analysis_payload["skew_25d_points"] = skew_points * 100
        if strategy == "SHORT_PUT" and abs(skew_points) > (max_skew / 100.0):
            return {
                "ticker": ticker.upper(),
                "timestamp": timestamp,
                "regime": regime,
                "analysis": analysis_payload,
                "recommendation": {"strategy": "NONE", "thesis": f"Skew gate: 25Δ skew {skew_points*100:.1f} pts > {max_skew}."},
            }
        contract = f"{ticker.upper()}{expiry_date.strftime('%y%m%d')}P{int(strike * 1000):08d}"
    else:
        raise DataFetchError(
            f"No option contract found for {ticker.upper()} in target delta band (0.20-0.30)."
        )

    # A-P5-03: Yield gate — Annualized_Yield > MIN_YIELD_PCT (e.g. 20%). Yield = (credit/strike)*(365/DTE)
    dte_days = (expiry_date - date.today()).days or 1
    annualized_yield = (credit_est / strike) * (Decimal("365") / Decimal(str(dte_days)))
    min_yield = Decimal(str(getattr(settings, "min_yield_pct", 0.20)))
    if strategy == "SHORT_PUT" and annualized_yield < min_yield:
        strategy = "NONE"
        recommendation_payload = {
            "strategy": "NONE",
            "thesis": f"Yield gate failed: annualized yield {annualized_yield:.2%} < {min_yield:.0%}.",
        }
        return {
            "ticker": ticker.upper(),
            "timestamp": timestamp,
            "regime": regime,
            "analysis": {**analysis_payload, "annualized_yield": annualized_yield},
            "recommendation": recommendation_payload,
        }

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

    # A-P5-05: Sector value exposure is enforced at the API layer (main.py) before persisting; not duplicated here.

    # Recompute expected move with the actual contract DTE — required for accurate safety check.
    expected_move_1sd = QuantLaws.calculate_expected_move(price, iv_30d, dte_days)
    analysis_payload["expected_move_1sd"] = float(expected_move_1sd)

    # 21 DTE Law: alert if the selected contract is already inside the exit window.
    dte_status = QuantLaws.check_21_dte(dte_days)
    analysis_payload["dte_status"] = dte_status
    analysis_payload["dte_days"] = dte_days

    safety_ok = strike < (price - expected_move_1sd)
    safety_check = "Strike is outside 1-SD expected move" if safety_ok else "Strike within 1-SD; review manually"
    analysis_payload["annualized_yield"] = annualized_yield

    # Risk Cap: max allowable loss is 3x the initial credit (hard stop-loss rule).
    stop_loss_trigger = (credit_est * Decimal("3")).quantize(Decimal("0.01"))

    # 50% Profit Rule: target close price for half-premium capture.
    profit_target_btc = (credit_est * Decimal("0.50")).quantize(Decimal("0.01"))

    recommendation_payload = {
        "strategy": strategy,
        "contract": contract,
        "strike": strike,
        "expiry": expiry_date.isoformat(),
        "delta": delta,
        "credit_est": credit_est.quantize(Decimal("0.01")),
        "buy_to_close_est": buy_to_close_est.quantize(Decimal("0.01")),
        # Risk management levels emitted alongside the trade recommendation.
        "stop_loss_trigger": stop_loss_trigger,   # Close if mark >= 3x entry credit
        "profit_target_btc": profit_target_btc,   # Close if mark <= 50% of entry credit
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
