# AI Advisor Bot — The Hunter (Phase 3)
# A-P3-01 S&P 500 loader, A-P3-02 Liquidity filter, A-P3-04 Earnings filter, A-P3-05 Sector cap, A-P3-06 Rate limit

from datetime import date
from typing import Any

# S&P 500: use static list or fetch from Wikipedia/API; liquidity/earnings from data provider


def load_sp500_universe(*, mock: bool = True) -> list[str]:
    """A-P3-01: Return list of S&P 500 tickers."""
    if mock:
        return _mock_sp500()
    return _fetch_sp500_constituents()


def _mock_sp500() -> list[str]:
    """Small subset for testing."""
    return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "SPY", "TSLA", "JPM", "V"]


def _fetch_sp500_constituents() -> list[str]:
    """Fetch from Wikipedia or data provider."""
    raise NotImplementedError("S&P 500 fetch not implemented. Use mock=True.")


def liquidity_filter(tickers: list[str], universe_metrics: dict[str, Any] | None = None) -> list[str]:
    """
    A-FIX-02 (Spec Patch v1.1): Stock universe filter strictly ADV > 5M.
    universe_metrics: { ticker: { "adv": float, "spread_pct": float } }. Mock passes all.
    """
    if not universe_metrics:
        return list(tickers)
    return [
        t for t in tickers
        if (universe_metrics.get(t) or {}).get("adv", 0) > 5_000_000
        and (universe_metrics.get(t) or {}).get("spread_pct", 0) < 1.5
    ]


def earnings_filter(ticker: str, earnings_date: date | None, trade_expiry: date, *, min_days_buffer: int = 7) -> bool:
    """
    A-P3-04: Exclude if earnings is within trade duration (before expiry).
    Returns False = exclude, True = ok to recommend.
    """
    if not earnings_date:
        return True
    if earnings_date >= trade_expiry:
        return True
    days_before_expiry = (trade_expiry - earnings_date).days
    return days_before_expiry >= min_days_buffer


def hard_earnings_exclusion(earnings_date: date | None, trade_expiry: date, today: date | None = None) -> bool:
    """
    A-FIX-03 (Spec Patch v1.1): Hard Earnings Exclusion.
    Return True if NO_TRADE (earnings between Today and Expiry); False if ok to trade.
    """
    from datetime import date as date_type
    today_val = today or date_type.today()
    if not earnings_date:
        return False  # no earnings → ok to trade
    if earnings_date < today_val:
        return False  # earnings in the past
    if earnings_date > trade_expiry:
        return False  # earnings after expiry
    return True  # earnings between today and expiry → NO_TRADE


def sector_cap_check(active_tickers_by_sector: dict[str, list[str]], sector: str, max_per_sector: int = 2) -> bool:
    """
    A-P3-05: Returns True if we can add another trade in this sector (max 2 per sector).
    """
    count = len(active_tickers_by_sector.get(sector, []))
    return count < max_per_sector


async def sector_value_exposure_allowed(
    db,  # AsyncSession
    sector: str,
    new_capital: float,
    max_sector_allocation_pct: float = 0.70,
) -> bool:
    """
    A-P5-05: Gate — block trade if Sum(Capital) in sector would exceed max_sector_allocation_pct of total.
    Returns True if adding this trade is allowed; False if it would exceed sector allocation.
    """
    from sqlalchemy import select
    from database.models import ActivePosition

    result = await db.execute(
        select(ActivePosition).where(ActivePosition.lifecycle_stage != "CLOSED")
    )
    positions = result.scalars().all()
    total_capital = 0.0
    sector_capital: dict[str, float] = {}
    for p in positions:
        entry = p.entry_data or {}
        cap = float(entry.get("capital_deployed") or 0.0)
        total_capital += cap
        sec = entry.get("sector") or "Unknown"
        sector_capital[sec] = sector_capital.get(sec, 0.0) + cap
    current_sector = sector_capital.get(sector, 0.0)
    new_total = total_capital + new_capital
    if new_total <= 0:
        return True
    new_sector_total = current_sector + new_capital
    share = new_sector_total / new_total
    return share <= max_sector_allocation_pct
