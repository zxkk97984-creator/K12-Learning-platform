"""add chapter_completions fact table (T13)

主动"完成本章"的唯一事实表：唯一约束 (student_id, chapter_id) 保证幂等，
source 区分主动完成与历史滚动事件回填（LEGACY_EVENT 仅迁移，不新增）。
"""  # noqa: E501

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e6f789"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chapter_completions",
        sa.Column("completion_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=16), server_default=sa.text("'EXPLICIT'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("completion_id"),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.student_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.chapter_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["book_id"], ["books.book_id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_chapter_completions_student_book",
        "chapter_completions",
        ["student_id", "book_id"],
    )
    op.create_index(
        "uq_chapter_completion_student_chapter",
        "chapter_completions",
        ["student_id", "chapter_id"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_chapter_completions_source",
        "chapter_completions",
        "source IN ('EXPLICIT','LEGACY_EVENT')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_chapter_completions_source", "chapter_completions", type_="check")
    op.drop_index("uq_chapter_completion_student_chapter", table_name="chapter_completions")
    op.drop_index("ix_chapter_completions_student_book", table_name="chapter_completions")
    op.drop_table("chapter_completions")
