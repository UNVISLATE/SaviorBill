"""lua template settings: lua_scripts.settings

Revision ID: 0007_lua_settings
Revises: 0006_referral
Create Date: 2026-07-01 18:00:00.000000

Настройки шаблона (ctx.lua.settings.*): общий JSON на скрипт, разделяемый всеми
услугами/провайдерами, которые его используют, чтобы не дублировать конфигурацию
(напр. учётные данные внешней панели) в каждой услуге.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_lua_settings"
down_revision = "0006_referral"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lua_scripts",
        sa.Column(
            "settings",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("lua_scripts", "settings")
