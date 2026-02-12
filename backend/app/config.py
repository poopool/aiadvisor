# AI Advisor Bot — Configuration
# A-P5-02: All strategy/watchman thresholds externalized; no hardcoded constants in QuantLaws/Watchman.
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings; overridable via environment."""

    database_url: str = "postgresql+asyncpg://aiadvisor:aiadvisor_dev@localhost:5432/aiadvisor"
    redis_url: str = "redis://localhost:6379/0"

    # Ingestion: set to True to use mock data (no API calls)
    ingestion_mock_mode: bool = True
    polygon_api_key: str = ""
    gemini_api_key: str = ""
    use_llm: bool = False

    # A-P2-08: Optional webhooks to send alerts and heartbeat to the human
    alert_webhook_url: str = ""
    heartbeat_webhook_url: str = ""

    # A-P5-01: Macro calendar — block new entries if high-impact event within lookahead
    macro_lookahead_hours: int = 48
    trading_economics_api_key: str = ""

    # A-P5-02: Quantitative / Strategy thresholds (externalized)
    iv_natr_min_ratio: float = 1.0
    dte_alert_threshold: int = 21
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0

    # A-P5-03: Refined entry gates (safety floor)
    rsi_entry_threshold: float = 40.0  # RSI must be < this for Short Put entry
    min_yield_pct: float = 0.20  # Annualized yield (e.g. 0.20 = 20%)

    # A-P5-04: Income Shield (roll logic)
    roll_itm_pct: float = 0.03  # (Price - Strike)/Strike > this → consider roll
    roll_dte_trigger: int = 14  # DTE < this and ITM → ROLL_NEEDED

    # A-P5-05: Sector value exposure
    max_sector_allocation_pct: float = 0.70  # Max share of total capital in one sector (70%)

    # A-P7-02: Volatility skew gate
    max_skew_threshold: float = 10.0  # Points; or 1.5x Call IV — block Short Put if skew above

    # Watchman data freshness (A-P2-07)
    data_stale_minutes: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
