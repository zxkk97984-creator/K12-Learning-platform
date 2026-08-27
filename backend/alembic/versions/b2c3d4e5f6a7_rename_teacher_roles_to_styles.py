"""rename teacher roles to style names

风格与形象解耦：teacher_roles 条目代表教学风格（可搭配任意教师形象），
name 不再使用英文代号（shuangling/strict-mentor），改为中文风格名。

"""

from typing import Sequence, Union

from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE teacher_roles
        SET name = '温暖鼓励', description = '以鼓励和引导为主的教学风格'
        WHERE role_id = '00000000-0000-0000-0000-000000000001' AND name <> '温暖鼓励'
        """
    )
    op.execute(
        """
        UPDATE teacher_roles
        SET name = '严谨清晰', description = '以逻辑和证据为主的教学风格'
        WHERE role_id = '00000000-0000-0000-0000-000000000002' AND name <> '严谨清晰'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE teacher_roles SET name = 'shuangling'
        WHERE role_id = '00000000-0000-0000-0000-000000000001'
        """
    )
    op.execute(
        """
        UPDATE teacher_roles SET name = 'strict-mentor'
        WHERE role_id = '00000000-0000-0000-0000-000000000002'
        """
    )
