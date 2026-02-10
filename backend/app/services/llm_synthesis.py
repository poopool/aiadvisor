# AI Advisor Bot — LLM Synthesis Layer (A-P1-06)
# Feeds technicals + option candidate to LLM for thesis generation. Stub + optional real.

from typing import Any

# Set OPENAI_API_KEY or similar for real synthesis; otherwise stub.


def synthesize_thesis(
    ticker: str,
    analysis: dict[str, Any],
    recommendation: dict[str, Any],
    *,
    use_llm: bool = False,
) -> str:
    """
    A-P1-06: Generate narrative thesis from technicals + option candidate.
    use_llm=True requires configured LLM API (e.g. OpenAI).
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
    """Call LLM API (OpenAI/Anthropic) with technicals + option; return thesis."""
    # import openai; ...
    raise NotImplementedError("LLM synthesis not configured. Set use_llm=False or configure OPENAI_API_KEY.")
