"""Phase 11: Watchtower 2.0 — P&L and Greeks columns on active_positions.

Revision ID: 005
Revises: 004
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("active_positions", sa.Column("market_value", sa.Numeric(14, 4), nullable=True))
    op.add_column("active_positions", sa.Column("unrealized_pnl", sa.Numeric(14, 4), nullable=True))
    op.add_column("active_positions", sa.Column("return_pct", sa.Numeric(10, 4), nullable=True))
    op.add_column("active_positions", sa.Column("greeks", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("active_positions", "greeks")
    op.drop_column("active_positions", "return_pct")
    op.drop_column("active_positions", "unrealized_pnl")
    op.drop_column("active_positions", "market_value")
