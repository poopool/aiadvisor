"""Add active_positions table and MarketData sma_50, sma_200.

Revision ID: 002
Revises: 001
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("market_data", sa.Column("sma_50", sa.Numeric(20, 4), nullable=True))
    op.add_column("market_data", sa.Column("sma_200", sa.Numeric(20, 4), nullable=True))
    op.create_table(
        "active_positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("lifecycle_stage", sa.String(32), nullable=False, server_default="MONITORING"),
        sa.Column("entry_data", JSONB, nullable=False),
        sa.Column("risk_rules", JSONB, nullable=False),
        sa.Column("last_heartbeat", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("active_positions")
    op.drop_column("market_data", "sma_200")
    op.drop_column("market_data", "sma_50")
