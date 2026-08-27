"""Phase 3: 阅读结算台账 + 学生统计秒数字段 + VOICE_SESSION_ENDED 事件类型

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reading_settlements",
        sa.Column("session_id", sa.UUID(), primary_key=True),
        sa.Column(
            "student_id",
            sa.UUID(),
            sa.ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "book_id",
            sa.UUID(),
            sa.ForeignKey("books.book_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("settled_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.add_column(
        "student_profiles",
        sa.Column(
            "total_learning_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # 存量数据回填：分钟 → 秒（历史值本身即真实累计的近似）
    op.execute(
        "UPDATE student_profiles SET total_learning_seconds = "
        "total_learning_minutes * 60 WHERE total_learning_seconds = 0"
    )

    # 扩展学习事件类型枚举（语音结束）
    op.execute(
        "ALTER TABLE learning_events DROP CONSTRAINT ck_learning_events_type"
    )
    op.execute(
        "ALTER TABLE learning_events ADD CONSTRAINT ck_learning_events_type "
        "CHECK (event_type IN ('CHAPTER_STARTED','CHAPTER_FINISHED','SECTION_READ',"
        "'KNOWLEDGE_CARD_VIEWED','HELP_REQUESTED','EXPLAIN_REQUESTED',"
        "'SUMMARY_REQUESTED','QUIZ_CREATED','QUIZ_ANSWERED','ANSWER_CORRECT',"
        "'ANSWER_WRONG','HINT_REQUESTED','QUESTION_ASKED','BOOK_STARTED',"
        "'BOOK_FINISHED','VOICE_SESSION_STARTED','VOICE_SESSION_ENDED',"
        "'ROLE_SWITCHED','TEXT_SELECTED'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE learning_events DROP CONSTRAINT ck_learning_events_type"
    )
    op.execute(
        "ALTER TABLE learning_events ADD CONSTRAINT ck_learning_events_type "
        "CHECK (event_type IN ('CHAPTER_STARTED','CHAPTER_FINISHED','SECTION_READ',"
        "'KNOWLEDGE_CARD_VIEWED','HELP_REQUESTED','EXPLAIN_REQUESTED',"
        "'SUMMARY_REQUESTED','QUIZ_CREATED','QUIZ_ANSWERED','ANSWER_CORRECT',"
        "'ANSWER_WRONG','HINT_REQUESTED','QUESTION_ASKED','BOOK_STARTED',"
        "'BOOK_FINISHED','VOICE_SESSION_STARTED','ROLE_SWITCHED','TEXT_SELECTED'))"
    )
    op.drop_column("student_profiles", "total_learning_seconds")
    op.drop_table("reading_settlements")
