# AI Advisor Bot — Async DB Session
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.base import Base
from database.models import ActivePosition, AlertLog, MarketData, TradeRecommendation  # noqa: F401

# Default for local Docker Compose; override via DATABASE_URL
DEFAULT_DATABASE_URL = "postgresql+asyncpg://aiadvisor:aiadvisor_dev@localhost:5432/aiadvisor"


def get_engine(database_url: str = DEFAULT_DATABASE_URL):
    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )


def get_session_factory(engine=None):
    if engine is None:
        engine = get_engine()
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def init_db(engine=None) -> None:
    """Create tables if they do not exist. For migrations, use Alembic."""
    if engine is None:
        engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
