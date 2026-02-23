# AI Advisor Bot — LLM Synthesis Layer (A-P1-06)
# The LLM acts solely as a synthesizer of unstructured context (news, sentiment,
# earnings narrative) against the quantitative data produced by the Python engine.
# It is strictly forbidden from performing technical analysis or calculating Greeks.

import json
import traceback
from decimal import Decimal
from typing import Any

import google.generativeai as genai

from app.config import settings

# ---------------------------------------------------------------------------
# System instruction — defines the LLM's immutable role and hard constraints.
# This is passed as system_instruction so it cannot be overridden by the data
# payload or future prompt injections.
# ---------------------------------------------------------------------------

_SYSTEM_INSTRUCTION = """\
You are a Quantitative Synthesis Engine for an options premium-selling advisory system.

YOUR ONLY JOB is to integrate unstructured context (news headlines, earnings narrative,
sector sentiment) with the quantitative JSON data supplied by the Python analytics engine.
You do NOT perform technical analysis. You do NOT calculate or estimate option Greeks,
implied volatility, expected moves, or any other quantitative metric. All numerical values
in your output must come verbatim from the provided JSON — you may NOT derive, adjust,
or infer new numbers.

ABSOLUTE PROHIBITIONS:
  1. Do not generate price targets, support/resistance levels, or chart patterns.
  2. Do not calculate, restate, or modify Delta, Gamma, Theta, Vega, or Rho.
  3. Do not calculate or modify IV, IV Rank, ATR, RSI, SMA, or any derived metric.
  4. Do not recommend entry or exit prices beyond what is in the JSON.
  5. Do not express a bullish or bearish directional opinion on the underlying stock.
  6. Do not fabricate news, earnings dates, or analyst ratings.
  7. If no unstructured context is provided, state "No external context available."
  8. If the strategy is NONE, explain only why the quantitative gates blocked the trade.

OUTPUT FORMAT — respond with a single valid JSON object and nothing else:
{
  "thesis_headline": "<One sentence: strategy, ticker, key gate result>",
  "quantitative_basis": "<One sentence: cite the exact metric values from JSON that cleared the gates>",
  "context_synthesis": "<One or two sentences: what the unstructured context adds or removes from conviction; must not contain any numbers not already in the JSON>",
  "risk_levels": {
    "stop_loss_trigger": "<value from JSON>",
    "profit_target_btc": "<value from JSON>",
    "dte_status": "<value from JSON>"
  },
  "confidence": "<HIGH | MEDIUM | LOW — based solely on completeness of the provided data>",
  "data_gaps": ["<list any fields that were null or missing in the input JSON>"]
}
"""


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def synthesize_thesis(
    ticker: str,
    analysis: dict[str, Any],
    recommendation: dict[str, Any],
    *,
    use_llm: bool = False,
    unstructured_context: str | None = None,
) -> str:
    """
    A-P1-06: Generate structured thesis from quantitative data + optional unstructured context.
    use_llm=True routes through Google Gemini (requires GEMINI_API_KEY).
    The LLM synthesizes context only — all quantitative values come from the Python engine.
    """
    if use_llm:
        return _synthesize_via_llm(ticker, analysis, recommendation, unstructured_context)
    return _stub_thesis(ticker, analysis, recommendation)


def _stub_thesis(ticker: str, analysis: dict[str, Any], recommendation: dict[str, Any]) -> str:
    """Deterministic stub from numbers (no LLM call)."""
    price = analysis.get("price")
    rsi = analysis.get("rsi_14")
    trend = analysis.get("trend", "")
    ratio = analysis.get("iv_natr_ratio")
    em = analysis.get("expected_move_1sd")
    strike = recommendation.get("strike")
    delta = recommendation.get("delta")
    stop_loss = recommendation.get("stop_loss_trigger")
    profit_tgt = recommendation.get("profit_target_btc")
    dte_status = analysis.get("dte_status", "N/A")
    parts = [f"{ticker} price {price}, RSI {rsi}, trend {trend}."]
    if ratio is not None:
        parts.append(f"IV/NATR ratio {ratio:.2f} (gate >= 1.5).")
    if em is not None:
        parts.append(f"Expected move (1-SD) {em:.2f}.")
    if strike is not None and delta is not None:
        parts.append(f"Strike {strike} at delta {delta}; outside 1-SD for premium sell.")
    if stop_loss is not None:
        parts.append(f"Stop-loss trigger: {stop_loss} (3x credit).")
    if profit_tgt is not None:
        parts.append(f"Profit target BTC: {profit_tgt} (50% credit).")
    parts.append(f"DTE status: {dte_status}.")
    return " ".join(parts)


def _synthesize_via_llm(
    ticker: str,
    analysis: dict[str, Any],
    recommendation: dict[str, Any],
    unstructured_context: str | None,
) -> str:
    """
    Call Google Gemini with a strict system instruction.
    The model receives clean JSON — no raw Python dicts, no Decimal objects.
    It may only synthesize unstructured_context against the provided numbers.
    """
    fallback = _stub_thesis(ticker, analysis, recommendation)
    if not settings.gemini_api_key:
        return fallback
    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=_SYSTEM_INSTRUCTION,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,      # deterministic; no creative inference
                top_p=1.0,
                max_output_tokens=512,
            ),
        )
        context_block = unstructured_context or "No external context available."
        user_message = (
            f"TICKER: {ticker}\n\n"
            f"QUANTITATIVE_DATA (Python engine output — treat as ground truth):\n"
            f"{json.dumps({'analysis': analysis, 'recommendation': recommendation}, cls=_DecimalEncoder, indent=2)}\n\n"
            f"UNSTRUCTURED_CONTEXT (news / earnings narrative — synthesize only):\n"
            f"{context_block}\n\n"
            "Produce the JSON thesis object as specified in your system instruction."
        )
        response = model.generate_content(user_message)
        if response and response.text:
            return response.text.strip()
        return fallback
    except Exception as e:
        print(f"LLM CRASH: {e}", flush=True)
        traceback.print_exc()
        return fallback
