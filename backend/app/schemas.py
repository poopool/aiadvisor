from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class StrategyType(str, Enum):
    SHORT_PUT = "SHORT_PUT"
    SHORT_CALL = "SHORT_CALL"


class ManualPositionCreate(BaseModel):
    """Schema for manually creating an ActivePosition."""

    ticker: str = Field(..., description="Stock ticker symbol (e.g., 'AAPL').")
    strategy: StrategyType = Field(..., description="The option strategy type.")
    short_strike: Decimal = Field(
        ..., gt=0, description="The short strike price of the option."
    )
    expiry_date: date = Field(..., description="The expiration date of the option.")
    entry_price: Decimal = Field(
        ..., gt=0, description="The credit received for entering the position."
    )
    contracts: int = Field(1, gt=0, description="The number of contracts.")
    sector: str | None = Field(
        "Unknown", description="The GICS sector of the underlying stock."
    )
    capital_deployed: float | None = Field(
        None,
        description="The capital required for the position. Auto-calculated if not provided.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "AMD",
                "strategy": "SHORT_PUT",
                "short_strike": "150.00",
                "expiry_date": "2026-03-20",
                "entry_price": "4.20",
                "contracts": 1,
                "sector": "Information Technology",
            }
        }
