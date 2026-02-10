"""Add alert_log for Watchman idempotency (A-P2-07).

Revision ID: 003
Revises: 002
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("trigger_type", sa.String(64), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("alert_log")
