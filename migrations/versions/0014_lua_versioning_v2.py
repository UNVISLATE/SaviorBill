"""lua v2: optimistic locking, дедуп версий, провенанс исполнения

Revision ID: 0014_lua_versioning_v2
Revises: 0013_totp
Create Date: 2026-08-02 01:00:00.000000

lua_scripts.lock_version — optimistic concurrency для PATCH/activate (не
даёт двум админам молча затереть правки друг друга). Индекс
(script_id, sha256) на lua_script_versions — быстрый дедуп при сохранении
("сохранить без правок" не плодит версии). user_services/payments +=
lua_script_version — какая версия скрипта реально исполнила последнее
действие (пин на услуге/провайдере мог с тех пор измениться).
"""

from alembic import op
import sqlalchemy as sa


revision = '0014_lua_versioning_v2'
down_revision = '0013_totp'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lua_scripts",
        sa.Column(
            "lock_version", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "ix_lua_script_versions_script_sha",
        "lua_script_versions",
        ["script_id", "sha256"],
    )
    op.add_column(
        "user_services",
        sa.Column("lua_script_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("lua_script_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "lua_script_version")
    op.drop_column("user_services", "lua_script_version")
    op.drop_index(
        "ix_lua_script_versions_script_sha", table_name="lua_script_versions"
    )
    op.drop_column("lua_scripts", "lock_version")
