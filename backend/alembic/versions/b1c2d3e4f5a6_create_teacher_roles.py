"""create teacher_roles and backfill deferred FKs

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-08-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teacher_roles",
        sa.Column(
            "role_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "persona",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("tone", sa.String(length=128), nullable=False),
        sa.Column("teaching_style", sa.String(length=128), nullable=False),
        sa.Column("avatar", sa.String(length=512), nullable=True),
        sa.Column(
            "sprite_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("voice_id", sa.String(length=128), nullable=True),
        sa.Column(
            "grade_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "prompt_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("interaction_style", sa.String(length=128), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
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
            "version >= 1",
            name="ck_teacher_roles_version",
        ),
        sa.PrimaryKeyConstraint("role_id"),
        sa.UniqueConstraint("name", name="uq_teacher_roles_name"),
    )

    op.execute(
        """
        INSERT INTO teacher_roles (
            role_id, name, description, persona, tone, teaching_style,
            sprite_manifest, grade_rules, prompt_profile, interaction_style, enabled
        ) VALUES
        (
            '00000000-0000-0000-0000-000000000001',
            'shuangling',
            '默认 AI 教师',
            '{"base_persona": "温暖耐心的 K12 数字教师", "character_persona": "霜铃"}',
            '温暖、鼓励',
            '从生活例子出发，逐步引导',
            '{"sheet_url": "", "grid_cols": 7, "grid_rows": 9, "states": {}}',
            '{"primary": "多用比喻", "junior": "强调理解", "senior": "引导迁移"}',
            '{"version": 1}',
            'interactive',
            true
        ),
        (
            '00000000-0000-0000-0000-000000000002',
            'strict-mentor',
            '严谨导师',
            '{"base_persona": "严谨理性的 K12 导师", "character_persona": "严谨导师"}',
            '严谨、清晰',
            '强调逻辑与证据',
            '{"sheet_url": "", "grid_cols": 7, "grid_rows": 9, "states": {}}',
            '{"primary": "建立规则", "junior": "强调推理", "senior": "批判思考"}',
            '{"version": 1}',
            'structured',
            true
        )
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE student_profiles SET current_teacher_role_id =
            '00000000-0000-0000-0000-000000000001'
        WHERE current_teacher_role_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE conversations SET teacher_role_id =
            '00000000-0000-0000-0000-000000000001'
        WHERE teacher_role_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM teacher_roles
            WHERE role_id = conversations.teacher_role_id
        )
        """
    )
    op.execute(
        """
        UPDATE quiz_sessions SET teacher_role_id =
            '00000000-0000-0000-0000-000000000001'
        WHERE teacher_role_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM teacher_roles
            WHERE role_id = quiz_sessions.teacher_role_id
        )
        """
    )
    op.execute(
        """
        UPDATE student_profiles SET current_teacher_role_id =
            '00000000-0000-0000-0000-000000000001'
        WHERE current_teacher_role_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM teacher_roles
            WHERE role_id = student_profiles.current_teacher_role_id
        )
        """
    )

    op.create_foreign_key(
        "fk_student_profiles_current_role",
        "student_profiles",
        "teacher_roles",
        ["current_teacher_role_id"],
        ["role_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_conversations_teacher_role",
        "conversations",
        "teacher_roles",
        ["teacher_role_id"],
        ["role_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_quiz_sessions_teacher_role",
        "quiz_sessions",
        "teacher_roles",
        ["teacher_role_id"],
        ["role_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quiz_sessions_teacher_role",
        "quiz_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_conversations_teacher_role",
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_student_profiles_current_role",
        "student_profiles",
        type_="foreignkey",
    )
    op.drop_table("teacher_roles")
