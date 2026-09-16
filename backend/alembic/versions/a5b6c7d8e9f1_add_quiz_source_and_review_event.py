"""Add T16 source FKs to quiz_sessions and QUIZ_REVIEW_COMPLETED event type.

Revision ID: a5b6c7d8e9f1
Revises: a4b5c6d7e8f9
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a5b6c7d8e9f1"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
depends_on: Union[str, Sequence[str], None] = None


def _old_constraint() -> sa.CheckConstraint:
    return sa.CheckConstraint(
        "event_type IN ('CHAPTER_STARTED','CHAPTER_FINISHED','SECTION_READ',"
        "'KNOWLEDGE_CARD_VIEWED','HELP_REQUESTED','EXPLAIN_REQUESTED',"
        "'SUMMARY_REQUESTED','QUIZ_CREATED','QUIZ_ANSWERED','ANSWER_CORRECT',"
        "'ANSWER_WRONG','HINT_REQUESTED','QUESTION_ASKED','BOOK_STARTED',"
        "'BOOK_FINISHED','VOICE_SESSION_STARTED','VOICE_SESSION_ENDED',"
        "'ROLE_SWITCHED','TEXT_SELECTED')",
        name="ck_learning_events_type",
    )


def _new_constraint() -> sa.CheckConstraint:
    return sa.CheckConstraint(
        "event_type IN ('CHAPTER_STARTED','CHAPTER_FINISHED','SECTION_READ',"
        "'KNOWLEDGE_CARD_VIEWED','HELP_REQUESTED','EXPLAIN_REQUESTED',"
        "'SUMMARY_REQUESTED','QUIZ_CREATED','QUIZ_ANSWERED','ANSWER_CORRECT',"
        "'ANSWER_WRONG','HINT_REQUESTED','QUESTION_ASKED','BOOK_STARTED',"
        "'BOOK_FINISHED','VOICE_SESSION_STARTED','VOICE_SESSION_ENDED',"
        "'ROLE_SWITCHED','TEXT_SELECTED','QUIZ_REVIEW_COMPLETED')",
        name="ck_learning_events_type",
    )


def upgrade() -> None:
    op.add_column(
        "quiz_sessions",
        sa.Column(
            "source_quiz_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "quiz_sessions",
        sa.Column(
            "source_question_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_quiz_sessions_source_session",
        "quiz_sessions",
        "quiz_sessions",
        ["source_quiz_session_id"],
        ["quiz_session_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_quiz_sessions_source_question",
        "quiz_sessions",
        "quiz_questions",
        ["source_question_id"],
        ["question_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_quiz_sessions_source_quiz",
        "quiz_sessions",
        ["source_quiz_session_id"],
    )

    op.drop_constraint("ck_learning_events_type", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_type",
        "learning_events",
        _new_constraint().sqltext,
    )


def downgrade() -> None:
    op.drop_constraint("ck_learning_events_type", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_type",
        "learning_events",
        _old_constraint().sqltext,
    )

    op.drop_index("ix_quiz_sessions_source_quiz", table_name="quiz_sessions")
    op.drop_constraint(
        "fk_quiz_sessions_source_question", "quiz_sessions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_quiz_sessions_source_session", "quiz_sessions", type_="foreignkey"
    )
    op.drop_column("quiz_sessions", "source_question_id")
    op.drop_column("quiz_sessions", "source_quiz_session_id")
