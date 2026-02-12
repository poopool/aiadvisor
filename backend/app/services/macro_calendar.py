# AI Advisor Bot — Macro Calendar Provider (A-P5-01)
# High-impact events (CPI, NFP, FOMC); gate: block new entries if event within MACRO_LOOKAHEAD_HOURS.

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any


class MacroCalendarProvider(ABC):
    """A-P5-01: Abstract provider for macro/economic calendar. Implementations: Mock, Trading Economics."""

    @abstractmethod
    def get_high_impact_events(self, within_hours: int = 48) -> list[dict[str, Any]]:
        """
        Return list of high-impact events in the next within_hours.
        Each item: { "start_time": datetime (UTC), "name": str, "importance": str, ... }.
        """
        ...


class MockMacroCalendarProvider(MacroCalendarProvider):
    """Mock: no events (gate passes)."""

    def get_high_impact_events(self, within_hours: int = 48) -> list[dict[str, Any]]:
        return []


class TradingEconomicsMacroCalendarProvider(MacroCalendarProvider):
    """Trading Economics API. Requires TRADING_ECONOMICS_API_KEY."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def get_high_impact_events(self, within_hours: int = 48) -> list[dict[str, Any]]:
        if not self._api_key:
            return []
        # Optional: requests.get(f"https://api.tradingeconomics.com/calendar?c={self._api_key}&importance=3")
        # For now, no external call to avoid new dependency; implement when key is set.
        return []


def get_macro_calendar_provider(mock: bool = True, api_key: str = "") -> MacroCalendarProvider:
    """Factory: returns Mock or Trading Economics provider."""
    if mock or not api_key:
        return MockMacroCalendarProvider()
    return TradingEconomicsMacroCalendarProvider(api_key)


def macro_event_gate_blocked(lookahead_hours: int, provider: MacroCalendarProvider | None = None) -> bool:
    """
    A-P5-01 Gate: Returns True if new entries should be BLOCKED (high-impact event within lookahead).
    Returns False if safe to open new trades.
    """
    if provider is None:
        from app.config import settings
        provider = get_macro_calendar_provider(
            mock=settings.ingestion_mock_mode,
            api_key=getattr(settings, "trading_economics_api_key", "") or "",
        )
    events = provider.get_high_impact_events(within_hours=lookahead_hours)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=lookahead_hours)
    for ev in events:
        start = ev.get("start_time")
        if start is None:
            continue
        if isinstance(start, str):
            try:
                start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except Exception:
                continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if now <= start <= cutoff:
            return True
    return False
