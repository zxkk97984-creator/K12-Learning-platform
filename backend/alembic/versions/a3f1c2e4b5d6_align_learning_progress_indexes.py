"""align learning progress index directions and coverage

Revision ID: a3f1c2e4b5d6
Revises: 52cd66eb864b
Create Date: 2026-08-19 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a3f1c2e4b5d6"
down_revision: Union[str, Sequence[str], None] = "52cd66eb864b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """对齐 0-E：时间索引改为 DESC，并补 quiz_session/conversation 索引。"""
    op.drop_index("ix_learning_sessions_student_started", table_name="learning_sessions")
    op.create_index(
        "ix_learning_sessions_student_started",
        "learning_sessions",
        [sa.text("student_id"), sa.text("started_at DESC")],
        unique=False,
    )
    op.drop_index("ix_learning_events_student_occurred", table_name="learning_events")
    op.create_index(
        "ix_learning_events_student_occurred",
        "learning_events",
        [sa.text("student_id"), sa.text("occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_learning_events_quiz_session",
        "learning_events",
        ["quiz_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_learning_events_conversation",
        "learning_events",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_learning_events_conversation", table_name="learning_events")
    op.drop_index("ix_learning_events_quiz_session", table_name="learning_events")
    op.drop_index("ix_learning_events_student_occurred", table_name="learning_events")
    op.create_index(
        "ix_learning_events_student_occurred",
        "learning_events",
        ["student_id", "occurred_at"],
        unique=False,
    )
    op.drop_index("ix_learning_sessions_student_started", table_name="learning_sessions")
    op.create_index(
        "ix_learning_sessions_student_started",
        "learning_sessions",
        ["student_id", "started_at"],
        unique=False,
    )
