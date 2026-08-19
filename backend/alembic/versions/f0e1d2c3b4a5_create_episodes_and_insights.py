"""create student episodes and profile insights

Revision ID: f0e1d2c3b4a5
Revises: e7f8a9b0c1d2
Create Date: 2026-08-19 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType


class VECTOR(UserDefinedType):
    """pgvector column binding; HNSW index intentionally deferred to Phase 8."""

    def get_col_spec(self, **kw):  # pragma: no cover
        return "VECTOR"


# revision identifiers, used by Alembic.
revision: str = "f0e1d2c3b4a5"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "student_episodes",
        sa.Column(
            "episode_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("book_id", sa.UUID(), nullable=True),
        sa.Column("chapter_id", sa.UUID(), nullable=True),
        sa.Column(
            "knowledge_point_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("embedding", VECTOR(), nullable=True),
        sa.Column("importance", sa.String(length=8), nullable=False),
        sa.Column(
            "tags",
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
            "importance IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_episodes_importance",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.student_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.book_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["chapters.chapter_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("episode_id"),
    )
    op.create_index(
        "ix_student_episodes_student_occurred",
        "student_episodes",
        ["student_id", sa.text("occurred_at DESC")],
        unique=False,
    )

    op.create_table(
        "profile_insights",
        sa.Column(
            "insight_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("insight_type", sa.String(length=24), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
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
            "insight_type IN ('STRENGTH','WEAKNESS','UNDERSTANDING','HABIT','CHANGE','INTEREST')",
            name="ck_profile_insights_type",
        ),
        sa.CheckConstraint(
            "level IN ('偏弱','一般','较稳定','较强','仍需观察')",
            name="ck_profile_insights_level",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUPERSEDED')",
            name="ck_profile_insights_status",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_profile_insights_valid_range",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.student_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("insight_id"),
    )
    op.create_index(
        "ix_profile_insights_student_status_valid",
        "profile_insights",
        ["student_id", "status", sa.text("valid_from DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_profile_insights_student_status_valid",
        table_name="profile_insights",
    )
    op.drop_table("profile_insights")
    op.drop_index(
        "ix_student_episodes_student_occurred",
        table_name="student_episodes",
    )
    op.drop_table("student_episodes")
