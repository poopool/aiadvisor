"""A-FIX-07: ActivePosition rolling lineage columns; A-FIX-09 decimal audit (already DECIMAL(10,4)+).

Revision ID: 004
Revises: 003
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("active_positions", sa.Column("parent_position_id", UUID(as_uuid=True), nullable=True))
    op.add_column("active_positions", sa.Column("root_position_id", UUID(as_uuid=True), nullable=True))
    op.add_column("active_positions", sa.Column("roll_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("active_positions", sa.Column("realized_pnl_pre_roll", sa.Numeric(14, 4), nullable=True))
    op.create_index("ix_active_positions_parent_position_id", "active_positions", ["parent_position_id"], unique=False)
    op.create_index("ix_active_positions_root_position_id", "active_positions", ["root_position_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_active_positions_root_position_id", "active_positions")
    op.drop_index("ix_active_positions_parent_position_id", "active_positions")
    op.drop_column("active_positions", "realized_pnl_pre_roll")
    op.drop_column("active_positions", "roll_count")
    op.drop_column("active_positions", "root_position_id")
    op.drop_column("active_positions", "parent_position_id")
