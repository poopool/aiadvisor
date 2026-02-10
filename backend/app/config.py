# AI Advisor Bot — Configuration
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings; overridable via environment."""

    database_url: str = "postgresql+asyncpg://aiadvisor:aiadvisor_dev@localhost:5432/aiadvisor"
    redis_url: str = "redis://localhost:6379/0"

    # Ingestion: set to True to use mock data (no API calls)
    ingestion_mock_mode: bool = True
    polygon_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
