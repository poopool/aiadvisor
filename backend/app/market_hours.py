# AI Advisor Bot — Market Hours (A-FIX-06)
# US equity/options: 9:30 AM - 4:00 PM Eastern, Mon–Fri

from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


def is_market_hours(utc_now: datetime | None = None) -> bool:
    """True if current time (ET) is within market hours on a weekday."""
    now = (utc_now or datetime.now(ZoneInfo("UTC"))).astimezone(ET)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE
