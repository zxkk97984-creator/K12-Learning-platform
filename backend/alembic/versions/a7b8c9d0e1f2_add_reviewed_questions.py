"""Add reviewed_questions table (T22b)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviewed_questions",
        sa.Column("question_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("stable_key", sa.String(128), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("grade_min", sa.Integer(), nullable=False),
        sa.Column("grade_max", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("review_status", sa.String(16), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("stable_key", name="uq_reviewed_questions_stable_key"),
        sa.CheckConstraint("review_status IN ('DRAFT','PENDING','APPROVED','REJECTED')", name="ck_reviewed_questions_status"),
        sa.CheckConstraint("grade_min >= 1", name="ck_reviewed_questions_grade_min"),
        sa.CheckConstraint("grade_max >= grade_min", name="ck_reviewed_questions_grade_range"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.chapter_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_reviewed_questions_chapter_grade", "reviewed_questions", ["chapter_id"])


def downgrade() -> None:
    op.drop_index("ix_reviewed_questions_chapter_grade", table_name="reviewed_questions")
    op.drop_table("reviewed_questions")
