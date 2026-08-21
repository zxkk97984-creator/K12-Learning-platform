"""allow mixed embedding dimensions for provider migration

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-08-21 00:00:00.000000

The mock provider uses 64 dimensions while real OpenAI-compatible providers
may return 768, 1024, or another configured dimension.  An unbounded pgvector
column preserves existing mock rows and lets a controlled re-index introduce a
new provider dimension.  HNSW indexes are removed because pgvector requires a
fixed dimension for vector indexes; search filters rows to the query dimension.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EMBEDDING_INDEXES = (
    ("ix_knowledge_chunks_embedding_hnsw", "knowledge_chunks"),
    ("ix_student_episodes_embedding_hnsw", "student_episodes"),
)


def upgrade() -> None:
    for index_name, table_name in _EMBEDDING_INDEXES:
        op.drop_index(index_name, table_name=table_name)

    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ALTER COLUMN embedding TYPE vector USING embedding::vector"
    )
    op.execute(
        "ALTER TABLE student_episodes "
        "ALTER COLUMN embedding TYPE vector USING embedding::vector"
    )


def downgrade() -> None:
    # vector(64) is the legacy schema.  A downgrade cannot represent a real
    # provider's wider vectors, so clear only incompatible embeddings and keep
    # legacy mock vectors.  Those rows can be re-indexed after rollback.
    op.execute(
        "UPDATE knowledge_chunks SET embedding = NULL "
        "WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 64"
    )
    op.execute(
        "UPDATE student_episodes SET embedding = NULL "
        "WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 64"
    )
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ALTER COLUMN embedding TYPE vector(64) "
        "USING embedding::vector(64)"
    )
    op.execute(
        "ALTER TABLE student_episodes "
        "ALTER COLUMN embedding TYPE vector(64) "
        "USING embedding::vector(64)"
    )

    for index_name, table_name in _EMBEDDING_INDEXES:
        op.create_index(
            index_name,
            table_name,
            ["embedding"],
            unique=False,
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )
