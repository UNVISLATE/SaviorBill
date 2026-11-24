"""lua_script_versions artifact columns and system_plugins table

Revision ID: 0003_lua_artifacts_and_plugins
Revises: 0002_scheduled_tasks
Create Date: 2026-11-24 22:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_lua_artifacts_and_plugins"
down_revision = "0002_scheduled_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lua_script_versions", sa.Column("code", sa.Text(), nullable=True))
    op.add_column(
        "lua_script_versions",
        sa.Column(
            "artifact_backend",
            sa.String(length=16),
            server_default="fs",
            nullable=False,
        ),
    )
    op.add_column(
        "lua_script_versions",
        sa.Column("artifact_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "lua_script_versions",
        sa.Column("artifact_blob", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "lua_script_versions",
        sa.Column(
            "has_native",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.create_table(
        "system_plugins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "bundle_backend",
            sa.String(length=16),
            server_default="fs",
            nullable=False,
        ),
        sa.Column("bundle_key", sa.String(length=255), nullable=True),
        sa.Column("bundle_blob", sa.LargeBinary(), nullable=True),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_system_plugins_slug", "system_plugins", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_system_plugins_slug", table_name="system_plugins")
    op.drop_table("system_plugins")
    op.drop_column("lua_script_versions", "has_native")
    op.drop_column("lua_script_versions", "artifact_blob")
    op.drop_column("lua_script_versions", "artifact_key")
    op.drop_column("lua_script_versions", "artifact_backend")
    op.drop_column("lua_script_versions", "code")
