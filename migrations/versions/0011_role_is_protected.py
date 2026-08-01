"""roles.is_protected — явный флаг неприкасаемой роли

Revision ID: 0011_role_is_protected
Revises: 0010_delivery_attempts
Create Date: 2026-08-02 00:00:00.000000

Защита владельца опиралась на сравнение строкового `roles.key == 'owner'`,
разбросанное по хендлерам (см. AUDIT.md §7.2). Явный флаг позволяет
распространить защиту на другие роли, не трогая код, и не зависит от
переименования ключей.

Флаг намеренно не выставляется через API: иначе администратор с `roles.edit`
пометил бы собственную роль защищённой и вышел из-под контроля владельца.
"""

from alembic import op
import sqlalchemy as sa


revision = '0011_role_is_protected'
down_revision = '0010_delivery_attempts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "is_protected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute("UPDATE roles SET is_protected = true WHERE key = 'owner'")


def downgrade() -> None:
    op.drop_column("roles", "is_protected")
