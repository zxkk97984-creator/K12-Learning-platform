"""create codelab domain (CodeLab Phase 1)

CodeLab = 霜铃的在线编程教学工具：编辑代码 → Docker 沙箱运行 → AI 编程评价。

三张表（详见 models.py 中的说明）：code_tasks / code_runs / code_reviews。

刻意不包含（留待下一阶段）：学习事件联动、课程编排、环境版本、
教师覆盖评分、多语言。本迁移**不修改任何既有表**，把未提交迁移的风险降到最低。
"""  # noqa: E501

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "code_tasks",
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("starter_code", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "test_groups",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("reference_solution", sa.Text(), nullable=True),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'DRAFT'"), nullable=False
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
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_code_tasks_status"
        ),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("slug", name="uq_code_tasks_slug"),
    )
    op.create_index(
        "ix_code_tasks_status_created",
        "code_tasks",
        ["status", sa.text("created_at DESC")],
    )

    op.create_table(
        "code_runs",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "outputs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('SUCCESS','FAILED','TIMEOUT','ERROR')", name="ck_code_runs_status"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["student_profiles.student_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["code_tasks.task_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_code_runs_student_created",
        "code_runs",
        ["student_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_code_runs_task_created", "code_runs", ["task_id", sa.text("created_at DESC")]
    )

    op.create_table(
        "code_reviews",
        sa.Column(
            "review_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'RUNNING'"), nullable=False
        ),
        sa.Column("grading_mode", sa.String(length=16), nullable=False),
        sa.Column(
            "deterministic_available",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("correctness_status", sa.String(length=16), nullable=False),
        sa.Column("functional_score", sa.Float(), nullable=True),
        sa.Column("robustness_score", sa.Float(), nullable=True),
        sa.Column("algorithm_score", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("final_score_100", sa.Float(), nullable=True),
        sa.Column(
            "deterministic_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "static_analysis",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ai_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("student_feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "needs_teacher_review",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("model_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            "status IN ('RUNNING','COMPLETED','FAILED','REVIEW_REQUIRED')",
            name="ck_code_reviews_status",
        ),
        sa.CheckConstraint(
            "correctness_status IN ('PASSED','PARTIAL','FAILED','NOT_VERIFIED')",
            name="ck_code_reviews_correctness",
        ),
        sa.CheckConstraint(
            "grading_mode IN ('tests','review_only')", name="ck_code_reviews_mode"
        ),
        # dai 缺陷 (a) 的数据库级兜底：LLM 无法把总分推到 [0,100] 之外
        sa.CheckConstraint(
            "final_score_100 IS NULL OR (final_score_100 >= 0 AND final_score_100 <= 100)",
            name="ck_code_reviews_final_score_range",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["code_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint("run_id", name="uq_code_reviews_run"),
    )
    op.create_index(
        "ix_code_reviews_status_created",
        "code_reviews",
        ["status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_code_reviews_status_created", table_name="code_reviews")
    op.drop_table("code_reviews")
    op.drop_index("ix_code_runs_task_created", table_name="code_runs")
    op.drop_index("ix_code_runs_student_created", table_name="code_runs")
    op.drop_table("code_runs")
    op.drop_index("ix_code_tasks_status_created", table_name="code_tasks")
    op.drop_table("code_tasks")
