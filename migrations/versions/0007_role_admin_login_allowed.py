"""roles.admin_login_allowed — явный флаг допуска роли в админку

Revision ID: 0007_role_admin_login_allowed
Revises: 0006_pg_trgm
Create Date: 2026-07-23 00:00:00.000000

Раньше допуск в админку определялся неявно — по наличию хоть одного perm
у роли (см. api/v1/admin/me.py). Явный флаг проще для UI (чекбокс в
редакторе роли) и не завязан на состав прав: можно временно отключить вход
для роли, не трогая её perms.
"""

from alembic import op
import sqlalchemy as sa


revision = '0007_role_admin_login_allowed'
down_revision = '0006_pg_trgm'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "admin_login_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Сохраняем прежнее поведение (гейт по наличию перм) для существующих
    # ролей на момент миграции — иначе все, кроме owner, потеряют доступ
    # сразу после деплоя. Дальше это уже явный флаг, редактируемый в UI.
    op.execute(
        "UPDATE roles SET admin_login_allowed = true "
        "WHERE key = 'owner' OR perms IS NOT NULL AND perms::text != '{}'"
    )


def downgrade() -> None:
    op.drop_column("roles", "admin_login_allowed")
