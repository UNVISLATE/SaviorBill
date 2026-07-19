"""settings.prefix — индексированный namespace-префикс ключа настройки

Revision ID: 0004_settings_prefix
Revises: 0003_banned_domains
Create Date: 2026-07-20 00:00:00.000000

Добавляет колонку `prefix` (первый '.'-сегмент `key`, например "smtp" для
"smtp.host") с индексом — SystemSettingsMngr.get_group() ищет по ней вместо
LIKE/startswith-скана всей таблицы. `key` остаётся PK/полным дотированным
ключом без изменений — composite PK (prefix, key) сознательно не делается,
слишком много мест напрямую делают `session.get(SystemSettingsModel, key)`
по полному ключу; см. models/system_settings.py.
"""

from alembic import op
import sqlalchemy as sa


revision = '0004_settings_prefix'
down_revision = '0003_banned_domains'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE settings ADD COLUMN prefix VARCHAR(64) "
        "GENERATED ALWAYS AS (split_part(key, '.', 1)) STORED"
    )
    op.create_index('ix_settings_prefix', 'settings', ['prefix'])


def downgrade() -> None:
    op.drop_index('ix_settings_prefix', table_name='settings')
    op.drop_column('settings', 'prefix')
