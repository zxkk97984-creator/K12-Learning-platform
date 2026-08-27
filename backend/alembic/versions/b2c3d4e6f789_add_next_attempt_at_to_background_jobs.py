"""add next_attempt_at to background_jobs for retry backoff"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e6f789"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 失败重试的指数退避：下次可被认领的最早时间。NULL 表示立即可认领。
    op.add_column(
        "background_jobs",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("background_jobs", "next_attempt_at")
