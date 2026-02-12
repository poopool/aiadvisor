# AI Advisor Bot — Batch Analysis Runner (A-P3-03)
# Run Phase 1 logic on liquid tickers with rate limiting and sector cap.

import asyncio
from datetime import date, timedelta
from typing import Any

from app.analysis import run_analysis
from app.services.universe import load_sp500_universe, liquidity_filter, earnings_filter, sector_cap_check
from app.services.rate_limit import get_rate_limiter, with_rate_limit


async def run_batch_analysis(
    db: Any,
    *,
    mock_ingestion: bool = True,
    max_tickers: int | None = 20,
) -> list[dict[str, Any]]:
    """
    A-P3-03: Run analysis on all liquid tickers from universe.
    Uses rate limiter (A-P3-06), earnings filter (A-P3-04), sector cap (A-P3-05).
    """
    tickers = load_sp500_universe(mock=mock_ingestion)
    if max_tickers:
        tickers = tickers[:max_tickers]

    limiter = get_rate_limiter(max_calls=5, window_sec=2.0)
    results: list[dict[str, Any]] = []
    active_by_sector: dict[str, list[str]] = {}

    for ticker in tickers:
        def _make_coro(t: str, db_session: Any):
            async def _run():
                return await asyncio.to_thread(run_analysis, t, db_session, mock_ingestion=mock_ingestion)
            return _run

        try:
            rec = await with_rate_limit(_make_coro(ticker, db), limiter=limiter)
            if not rec or rec.get("no_trade") or rec.get("recommendation") is None:
                continue
            sector = (rec.get("analysis") or {}).get("sector") or "Unknown"
            if not sector_cap_check(active_by_sector, sector):
                continue
            expiry_str = (rec.get("recommendation") or {}).get("expiry")
            earnings_date = (rec.get("analysis") or {}).get("earnings_date")
            if expiry_str:
                exp = date.fromisoformat(expiry_str)
                if not earnings_filter(ticker, earnings_date, exp):
                    continue
            results.append(rec)
            active_by_sector.setdefault(sector, []).append(ticker)
        except Exception:
            continue

    return results
