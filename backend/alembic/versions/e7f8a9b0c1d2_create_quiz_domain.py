"""create quiz sessions, questions, answers, and interactions

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-08-19 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_sessions",
        sa.Column(
            "quiz_session_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        # FK→teacher_roles 延迟 Phase 11；角色表尚未落地，本列可空且不建 FK。
        sa.Column("teacher_role_id", sa.UUID(), nullable=True),
        sa.Column("book_id", sa.UUID(), nullable=True),
        sa.Column("chapter_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("quiz_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'GENERATING'"),
            nullable=False,
        ),
        sa.Column(
            "questions_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "duration_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("ai_feedback", sa.Text(), nullable=True),
        sa.Column("model_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("skill_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "quiz_kind IN ('CHAPTER_QUIZ','AI_QUIZ')",
            name="ck_quiz_sessions_kind",
        ),
        sa.CheckConstraint(
            "status IN ('GENERATING','ACTIVE','COMPLETED','ABANDONED')",
            name="ck_quiz_sessions_status",
        ),
        sa.CheckConstraint(
            "duration_seconds >= 0", name="ck_quiz_sessions_duration"
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_quiz_sessions_completed_after_created",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["student_profiles.student_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["book_id"], ["books.book_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["chapter_id"], ["chapters.chapter_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("quiz_session_id"),
    )
    op.create_index(
        "ix_quiz_sessions_student_created",
        "quiz_sessions",
        ["student_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_quiz_sessions_conversation",
        "quiz_sessions",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_quiz_sessions_book_chapter",
        "quiz_sessions",
        ["book_id", "chapter_id"],
        unique=False,
    )

    op.create_table(
        "quiz_questions",
        sa.Column(
            "question_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("quiz_session_id", sa.UUID(), nullable=False),
        sa.Column("question_order", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(length=24), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "correct_answer", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "source_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "interaction_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{\"allow_hint\": true, \"max_hint_level\": 3}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_point_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "question_type IN ('SINGLE_CHOICE','MULTIPLE_CHOICE','TRUE_FALSE','FILL_BLANK')",
            name="ck_quiz_questions_type",
        ),
        sa.ForeignKeyConstraint(
            ["quiz_session_id"],
            ["quiz_sessions.quiz_session_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("question_id"),
        sa.UniqueConstraint(
            "quiz_session_id", "question_order", name="uq_quiz_questions_session_order"
        ),
    )

    op.create_table(
        "quiz_answers",
        sa.Column(
            "answer_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("quiz_session_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column(
            "submitted_answer", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column(
            "hint_level_at_submit",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_final", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempt_no >= 1", name="ck_quiz_answers_attempt_no"),
        sa.CheckConstraint(
            "hint_level_at_submit >= 0", name="ck_quiz_answers_hint_level"
        ),
        sa.ForeignKeyConstraint(
            ["quiz_session_id"],
            ["quiz_sessions.quiz_session_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["quiz_questions.question_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["student_profiles.student_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("answer_id"),
        sa.UniqueConstraint(
            "quiz_session_id",
            "question_id",
            "attempt_no",
            name="uq_quiz_answers_attempt",
        ),
    )
    op.create_index(
        "ix_quiz_answers_session_question_created",
        "quiz_answers",
        ["quiz_session_id", "question_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "quiz_interactions",
        sa.Column(
            "interaction_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("quiz_session_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=True),
        sa.Column("interaction_type", sa.String(length=24), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("answer_id", sa.UUID(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "interaction_type IN ('HINT_REQUEST','HINT_RESPONSE','QUESTION_ASK',"
            "'TEACHER_REPLY','ANSWER_SUBMIT','ANSWER_RESULT')",
            name="ck_quiz_interactions_type",
        ),
        sa.ForeignKeyConstraint(
            ["quiz_session_id"],
            ["quiz_sessions.quiz_session_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["quiz_questions.question_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.message_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"], ["quiz_answers.answer_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("interaction_id"),
        sa.UniqueConstraint(
            "quiz_session_id",
            "sequence",
            name="uq_quiz_interactions_session_sequence",
        ),
    )
    op.create_index(
        "ix_quiz_interactions_session_question_created",
        "quiz_interactions",
        ["quiz_session_id", "question_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_quiz_interactions_message", "quiz_interactions", ["message_id"], unique=False
    )
    op.create_index(
        "ix_quiz_interactions_answer", "quiz_interactions", ["answer_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_interactions_answer", table_name="quiz_interactions")
    op.drop_index("ix_quiz_interactions_message", table_name="quiz_interactions")
    op.drop_index(
        "ix_quiz_interactions_session_question_created", table_name="quiz_interactions"
    )
    op.drop_table("quiz_interactions")
    op.drop_index("ix_quiz_answers_session_question_created", table_name="quiz_answers")
    op.drop_table("quiz_answers")
    op.drop_table("quiz_questions")
    op.drop_index("ix_quiz_sessions_book_chapter", table_name="quiz_sessions")
    op.drop_index("ix_quiz_sessions_conversation", table_name="quiz_sessions")
    op.drop_index("ix_quiz_sessions_student_created", table_name="quiz_sessions")
    op.drop_table("quiz_sessions")
