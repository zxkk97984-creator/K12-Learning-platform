"""Add message_covered_count to conversation_summaries (T20 20a).

Revision ID: a6b7c8d9e0f1
Revises: a5b6c7d8e9f1
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f1"
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_summaries",
        sa.Column("message_covered_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("conversation_summaries", "message_covered_count")
