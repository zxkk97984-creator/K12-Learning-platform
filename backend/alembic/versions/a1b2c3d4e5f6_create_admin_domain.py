"""create admins and idempotency keys, backfill deferred FKs

Revision ID: a1b2c3d4e5f6
Revises: a2b3c4d5e6f7
Create Date: 2026-08-19 23:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column(
            "admin_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column(
            "role_level",
            sa.String(length=24),
            server_default=sa.text("'SUPERVISOR'"),
            nullable=False,
        ),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
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
            "role_level IN ('SUPERVISOR','CONTENT_EDITOR')",
            name="ck_admins_role_level",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("admin_id"),
        sa.UniqueConstraint("user_id", name="uq_admins_user"),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column(
            "idempotency_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "response",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('STUDENT','ADMIN')",
            name="ck_idempotency_keys_actor_type",
        ),
        sa.PrimaryKeyConstraint("idempotency_id"),
        sa.UniqueConstraint(
            "actor_id",
            "actor_type",
            "key",
            name="uq_idempotency_keys_actor_key",
        ),
    )
    op.create_index(
        "ix_idempotency_keys_actor_expires",
        "idempotency_keys",
        ["actor_id", "expires_at"],
        unique=False,
    )

    # Backfill the demo admin user (idempotent; fresh DBs may have none yet).
    op.execute(
        """
        INSERT INTO admins (user_id, display_name, role_level, enabled)
        SELECT user_id, username, 'SUPERVISOR', true FROM users
        WHERE username = 'admin'
        ON CONFLICT (user_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE books SET created_by = (
            SELECT admin_id FROM admins ORDER BY created_at LIMIT 1
        ) WHERE created_by IS NULL
        """
    )
    op.execute(
        """
        UPDATE knowledge_resources SET uploaded_by = (
            SELECT admin_id FROM admins ORDER BY created_at LIMIT 1
        ) WHERE uploaded_by IS NULL
        """
    )

    op.create_foreign_key(
        "fk_books_created_by_admin",
        "books",
        "admins",
        ["created_by"],
        ["admin_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_knowledge_resources_uploaded_by_admin",
        "knowledge_resources",
        "admins",
        ["uploaded_by"],
        ["admin_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_knowledge_resources_uploaded_by_admin",
        "knowledge_resources",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_books_created_by_admin",
        "books",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_idempotency_keys_actor_expires",
        table_name="idempotency_keys",
    )
    op.drop_table("idempotency_keys")
    op.drop_table("admins")
