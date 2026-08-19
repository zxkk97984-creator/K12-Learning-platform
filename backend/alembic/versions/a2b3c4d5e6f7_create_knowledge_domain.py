"""create knowledge resources and chunks with pgvector HNSW indexes

Revision ID: a2b3c4d5e6f7
Revises: f0e1d2c3b4a5
Create Date: 2026-08-19 23:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType


class VECTOR(UserDefinedType):
    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw):  # pragma: no cover
        return f"VECTOR({self.dimensions})" if self.dimensions else "VECTOR"


# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f0e1d2c3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_resources",
        sa.Column(
            "resource_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("license", sa.String(length=128), nullable=False),
        sa.Column("copyright_status", sa.String(length=128), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'UPLOADED'"),
            nullable=False,
        ),
        # FK→admins 延迟 Phase 10 补（0-E 已裁定）
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
        sa.CheckConstraint(
            "file_type IN ('PDF','MARKDOWN','TXT','HTML')",
            name="ck_knowledge_resources_file_type",
        ),
        sa.CheckConstraint(
            "status IN ('UPLOADED','PARSING','CHUNKING','INDEXING','READY','FAILED')",
            name="ck_knowledge_resources_status",
        ),
        sa.PrimaryKeyConstraint("resource_id"),
    )
    op.create_index(
        "ix_knowledge_resources_status_created",
        "knowledge_resources",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_resources_uploaded_by",
        "knowledge_resources",
        ["uploaded_by"],
        unique=False,
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column(
            "chunk_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_point_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("embedding", VECTOR(64), nullable=True),
        sa.Column(
            "token_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "token_count >= 0",
            name="ck_knowledge_chunks_token_count",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','READY','FAILED')",
            name="ck_knowledge_chunks_status",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["knowledge_resources.resource_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.UniqueConstraint(
            "resource_id",
            "chunk_index",
            name="uq_knowledge_chunks_resource_index",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.execute(
        "ALTER TABLE student_episodes ALTER COLUMN embedding TYPE vector(64)"
    )
    op.create_index(
        "ix_student_episodes_embedding_hnsw",
        "student_episodes",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_episodes_embedding_hnsw",
        table_name="student_episodes",
    )
    op.execute(
        "ALTER TABLE student_episodes ALTER COLUMN embedding TYPE vector"
    )
    op.drop_index(
        "ix_knowledge_chunks_embedding_hnsw",
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")
    op.drop_index(
        "ix_knowledge_resources_uploaded_by",
        table_name="knowledge_resources",
    )
    op.drop_index(
        "ix_knowledge_resources_status_created",
        table_name="knowledge_resources",
    )
    op.drop_table("knowledge_resources")
