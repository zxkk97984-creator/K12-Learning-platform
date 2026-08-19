"""create conversations, messages, and conversation_summaries

Revision ID: c4d5e6f7a8b9
Revises: a3f1c2e4b5d6
Create Date: 2026-08-19 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "a3f1c2e4b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column(
            "conversation_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.UUID(), nullable=False),
        # FK→teacher_roles 延迟到 Phase 11；0-E 定义为非空，本阶段因角色表未落地放宽为可空。
        sa.Column("teacher_role_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'ACTIVE'"), nullable=False
        ),
        sa.Column(
            "channel", sa.String(length=16), server_default=sa.text("'TEXT'"), nullable=False
        ),
        sa.Column(
            "current_page_context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "recent_messages",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE','ARCHIVED','DELETED')", name="ck_conversations_status"
        ),
        sa.CheckConstraint(
            "channel IN ('TEXT','VOICE')", name="ck_conversations_channel"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["student_profiles.student_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_conversations_student_updated",
        "conversations",
        ["student_id", sa.text("updated_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_conversations_teacher_role",
        "conversations",
        ["teacher_role_id"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column(
            "message_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("model_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('STUDENT','TEACHER','SYSTEM')", name="ck_messages_role"
        ),
        sa.CheckConstraint(
            "type IN ('TEXT','QUIZ','TOOL_STATUS','HINT','RECOMMENDATION',"
            "'SYSTEM','LEARNING_SUMMARY')",
            name="ck_messages_type",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.conversation_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_messages_conversation_sequence"
        ),
    )

    op.create_table(
        "conversation_summaries",
        sa.Column(
            "summary_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "token_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "summary_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "source_message_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("model_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint(
            "token_count >= 0", name="ck_conversation_summaries_token_count"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.conversation_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("summary_id"),
        sa.UniqueConstraint(
            "conversation_id", name="uq_conversation_summaries_conversation"
        ),
    )


def downgrade() -> None:
    op.drop_table("conversation_summaries")
    op.drop_table("messages")
    op.drop_index("ix_conversations_teacher_role", table_name="conversations")
    op.drop_index("ix_conversations_student_updated", table_name="conversations")
    op.drop_table("conversations")
