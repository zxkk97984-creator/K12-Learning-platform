"""add recommendation D9 traceability fields and EXPIRED status"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # D9 溯源字段（平铺列，对齐 Book.source_ids/license/copyright_status 惯例）：
    # source_ids / license / source_url 记录推荐所引用的知识来源；model_info /
    # skill_version 记录这条推荐由哪版规则/模型生成；expires_at 支持 EXPIRED 状态。
    op.add_column(
        "recommendations",
        sa.Column(
            "source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "recommendations", sa.Column("license", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "recommendations", sa.Column("source_url", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "recommendations", sa.Column("model_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "recommendations", sa.Column("skill_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "recommendations", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )

    # 扩展状态枚举：加入 EXPIRED。
    op.drop_constraint("ck_recommendations_status", "recommendations", type_="check")
    op.create_check_constraint(
        "ck_recommendations_status",
        "recommendations",
        "status IN ('ACTIVE','DISMISSED','EXPIRED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_recommendations_status", "recommendations", type_="check")
    op.create_check_constraint(
        "ck_recommendations_status",
        "recommendations",
        "status IN ('ACTIVE','DISMISSED')",
    )
    op.drop_column("recommendations", "expires_at")
    op.drop_column("recommendations", "skill_version")
    op.drop_column("recommendations", "model_info")
    op.drop_column("recommendations", "source_url")
    op.drop_column("recommendations", "license")
    op.drop_column("recommendations", "source_ids")
