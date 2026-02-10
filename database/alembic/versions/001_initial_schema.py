"""Initial schema: market_data, trade_recommendations.

Revision ID: 001
Revises:
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_data",
        sa.Column("ticker", sa.String(16), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("close", sa.Numeric(20, 4), nullable=False),
        sa.Column("atr_14", sa.Numeric(20, 4), nullable=True),
        sa.Column("rsi_14", sa.Numeric(8, 2), nullable=True),
        sa.Column("iv_30d", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "trade_recommendations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False, index=True),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("strike", sa.Numeric(20, 4), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("calculated_metrics", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("trade_recommendations")
    op.drop_table("market_data")
