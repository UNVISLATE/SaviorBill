"""lua_script_versions — история версий Lua-скриптов + выбор версии в связях

Revision ID: 0008_lua_script_versions
Revises: 0007_role_admin_login_allowed
Create Date: 2026-07-25 00:00:00.000000

Каждое изменение кода скрипта создаёт новую immutable-версию (номер = старый+1)
вместо перезатирания файла. Услуги/платёжки/oauth-провайдеры получают
опциональный ``script_version`` (NULL = latest, число = конкретная версия;
если версия удалена — тихий фоллбэк на latest в резолвере на уровне кода).
"""

from alembic import op
import sqlalchemy as sa


revision = '0008_lua_script_versions'
down_revision = '0007_role_admin_login_allowed'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lua_scripts",
        sa.Column(
            "current_version", sa.Integer(), nullable=False, server_default="1"
        ),
    )

    op.create_table(
        "lua_script_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("commit_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["script_id"], ["lua_scripts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("script_id", "version"),
    )
    op.create_index(
        op.f("ix_lua_script_versions_script_id"),
        "lua_script_versions",
        ["script_id"],
        unique=False,
    )

    # Обратная совместимость: у уже существующих скриптов создаём v1 из их
    # текущего файла, чтобы список версий не был пустым.
    op.execute(
        "INSERT INTO lua_script_versions (script_id, version, filename, sha256, "
        "commit_message, created_at) "
        "SELECT id, 1, filename, sha256, 'Начальная версия', created_at "
        "FROM lua_scripts"
    )

    op.add_column(
        "services", sa.Column("lua_script_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "pay_providers", sa.Column("script_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "oauth_cfg", sa.Column("script_version", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("oauth_cfg", "script_version")
    op.drop_column("pay_providers", "script_version")
    op.drop_column("services", "lua_script_version")

    op.drop_index(
        op.f("ix_lua_script_versions_script_id"), table_name="lua_script_versions"
    )
    op.drop_table("lua_script_versions")

    op.drop_column("lua_scripts", "current_version")
