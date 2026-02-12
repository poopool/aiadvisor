# AI Advisor Bot — LLM Synthesis Layer (A-P1-06)
# Feeds technicals + option candidate to LLM for thesis generation. Stub or Google Gemini.

import traceback
from typing import Any

import google.generativeai as genai

from app.config import settings


def synthesize_thesis(
    ticker: str,
    analysis: dict[str, Any],
    recommendation: dict[str, Any],
    *,
    use_llm: bool = False,
) -> str:
    """
    A-P1-06: Generate narrative thesis from technicals + option candidate.
    use_llm=True uses Google Gemini (requires GEMINI_API_KEY).
    """
    if use_llm:
        return _synthesize_via_llm(ticker, analysis, recommendation)
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
    parts = [f"{ticker} price {price}, RSI {rsi}, trend {trend}."]
    if ratio is not None:
        parts.append(f"IV/NATR ratio {ratio:.2f}.")
    if em is not None:
        parts.append(f"Expected move (1-SD) {em:.2f}.")
    if strike is not None and delta is not None:
        parts.append(f"Strike {strike} at delta {delta}; outside 1-SD for premium sell.")
    return " ".join(parts)


def _synthesize_via_llm(ticker: str, analysis: dict[str, Any], recommendation: dict[str, Any]) -> str:
    """Call Google Gemini with technicals + option; return a concise trading thesis."""
    fallback = _stub_thesis(ticker, analysis, recommendation)
    if not settings.gemini_api_key:
        return fallback
    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = (
            "You are a professional options analyst. Based strictly on the following data, "
            "write a concise, professional trading thesis (2–4 sentences) explaining why this Short Put "
            "is a good idea. Use only the provided math and metrics; do not invent numbers.\n\n"
            f"Ticker: {ticker}\n\n"
            f"Analysis: {analysis}\n\n"
            f"Recommendation: {recommendation}\n\n"
            "Thesis:"
        )
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        return fallback
    except Exception as e:
        print(f"LLM CRASH: {e}", flush=True)
        traceback.print_exc()
        return fallback
