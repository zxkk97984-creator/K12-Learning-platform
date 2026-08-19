"""create student memories, memory candidates, and memory evidence

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-19 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Candidates are created first because student_memories.origin_candidate_id
    # points to this table with ON DELETE SET NULL.
    op.create_table(
        "memory_candidates",
        sa.Column(
            "candidate_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("candidate_type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "proposed_memory",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column(
            "model_info",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "candidate_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')",
            name="ck_memory_candidates_type",
        ),
        sa.CheckConstraint(
            "confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_memory_candidates_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','MERGED')",
            name="ck_memory_candidates_status",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.student_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_index(
        "ix_memory_candidates_student_status",
        "memory_candidates",
        ["student_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_memory_candidates_status_created",
        "memory_candidates",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "student_memories",
        sa.Column(
            "memory_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("memory_type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "evidence_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("origin_candidate_id", sa.UUID(), nullable=True),
        sa.Column(
            "user_confirmed",
            sa.Boolean(),
            server_default=sa.text("false"),
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
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "memory_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')",
            name="ck_student_memories_type",
        ),
        sa.CheckConstraint(
            "confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_memories_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','DISPUTED','SUPERSEDED','REMOVED')",
            name="ck_student_memories_status",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.student_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_candidate_id"],
            ["memory_candidates.candidate_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("memory_id"),
    )
    op.create_index(
        "ix_student_memories_student_status",
        "student_memories",
        ["student_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_student_memories_student_updated",
        "student_memories",
        ["student_id", sa.text("updated_at DESC")],
        unique=False,
    )

    op.create_table(
        "memory_evidence",
        sa.Column(
            "evidence_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column(
            "event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "count", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("first_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("derived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('QUIZ','LEARNING_SESSION','CONVERSATION','BOOK_PROGRESS')",
            name="ck_memory_evidence_source_type",
        ),
        sa.CheckConstraint("count >= 1", name="ck_memory_evidence_count"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.student_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index(
        "ix_memory_evidence_student_derived",
        "memory_evidence",
        ["student_id", sa.text("derived_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memory_evidence_student_derived", table_name="memory_evidence")
    op.drop_table("memory_evidence")
    op.drop_index(
        "ix_student_memories_student_updated", table_name="student_memories"
    )
    op.drop_index(
        "ix_student_memories_student_status", table_name="student_memories"
    )
    op.drop_table("student_memories")
    op.drop_index(
        "ix_memory_candidates_status_created", table_name="memory_candidates"
    )
    op.drop_index(
        "ix_memory_candidates_student_status", table_name="memory_candidates"
    )
    op.drop_table("memory_candidates")
