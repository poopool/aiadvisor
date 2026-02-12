# AI Advisor Bot — Configuration
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
