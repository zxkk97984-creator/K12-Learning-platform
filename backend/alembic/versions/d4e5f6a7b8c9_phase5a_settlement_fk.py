"""Phase 5-B-I：补齐 reading_settlements.session_id → learning_sessions 外键

c3d4e5f6a7b8 创建 reading_settlements 时遗漏了该 FK（模型已声明），
导致 alembic check 报迁移漂移。本迁移仅添加约束，不改数据。

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "fk_reading_settlements_session"


def upgrade() -> None:
    op.create_foreign_key(
        _CONSTRAINT_NAME,
        source_table="reading_settlements",
        referent_table="learning_sessions",
        local_cols=["session_id"],
        remote_cols=["session_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "reading_settlements", type_="foreignkey")
