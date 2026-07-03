"""script FKs RESTRICT + oauth_cfg lua fields

Revision ID: 0009_script_guard_oauth
Revises: 0008_media_pipeline
Create Date: 2026-07-15 12:00:00.000000

Раздел 4 (безопасность) + подготовка Раздела 2 (OAuth через Lua):
- FK на lua_scripts у services/pay_providers/oauth_cfg → ondelete=RESTRICT, чтобы
  нельзя было удалить скрипт, пока он используется;
- oauth_cfg: единый ``script_id`` (RESTRICT) + зашифрованный ``secrets_enc``; поля
  ``client_id``/``client_secret_enc`` становятся необязательными (Lua-провайдеры
  хранят креды в ``secrets_enc``).
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_script_guard_oauth"
down_revision = "0008_media_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # services.lua_script_id: SET NULL -> RESTRICT.
    op.drop_constraint("services_lua_script_id_fkey", "services", type_="foreignkey")
    op.create_foreign_key(
        "fk_services_lua_script_id",
        "services",
        "lua_scripts",
        ["lua_script_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # pay_providers.script_id: SET NULL -> RESTRICT (имя FK задано в 0004).
    op.drop_constraint(
        "fk_pay_providers_script_id", "pay_providers", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_pay_providers_script_id",
        "pay_providers",
        "lua_scripts",
        ["script_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # oauth_cfg: новые поля для Lua-флоу.
    op.add_column("oauth_cfg", sa.Column("script_id", sa.Integer(), nullable=True))
    op.add_column(
        "oauth_cfg",
        sa.Column("secrets_enc", sa.Text(), server_default="", nullable=False),
    )
    op.create_index(
        op.f("ix_oauth_cfg_script_id"), "oauth_cfg", ["script_id"], unique=False
    )
    op.create_foreign_key(
        "fk_oauth_cfg_script_id",
        "oauth_cfg",
        "lua_scripts",
        ["script_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "oauth_cfg", "client_id", existing_type=sa.String(255), nullable=True
    )
    op.alter_column(
        "oauth_cfg", "client_secret_enc", existing_type=sa.Text(), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        "oauth_cfg", "client_secret_enc", existing_type=sa.Text(), nullable=False
    )
    op.alter_column(
        "oauth_cfg", "client_id", existing_type=sa.String(255), nullable=False
    )
    op.drop_constraint("fk_oauth_cfg_script_id", "oauth_cfg", type_="foreignkey")
    op.drop_index(op.f("ix_oauth_cfg_script_id"), table_name="oauth_cfg")
    op.drop_column("oauth_cfg", "secrets_enc")
    op.drop_column("oauth_cfg", "script_id")

    op.drop_constraint(
        "fk_pay_providers_script_id", "pay_providers", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_pay_providers_script_id",
        "pay_providers",
        "lua_scripts",
        ["script_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("fk_services_lua_script_id", "services", type_="foreignkey")
    op.create_foreign_key(
        "services_lua_script_id_fkey",
        "services",
        "lua_scripts",
        ["lua_script_id"],
        ["id"],
        ondelete="SET NULL",
    )
