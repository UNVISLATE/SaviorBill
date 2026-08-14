"""roles.allow_login — явный флаг допуска роли к получению токенов

Revision ID: 0018_role_allow_login
Revises: 0017_admin_self_service
Create Date: 2026-08-14 00:00:00.000000

Раньше бан пользователя не блокировал выдачу токенов вообще (роль
``banned`` и так лишена прав через RBAC). Этот флаг даёт возможность явно
запретить логин/refresh для конкретной роли, не трогая её ``perms`` — по
аналогии с ``admin_login_allowed`` (0007), но для входа в API вообще, а не
только в админку. По умолчанию ``true`` (не меняет поведение существующих
ролей), кроме роли ``banned`` — для неё выставляем ``false`` сразу.
"""

from alembic import op
import sqlalchemy as sa


revision = '0018_role_allow_login'
down_revision = '0017_admin_self_service'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "allow_login",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.execute("UPDATE roles SET allow_login = false WHERE key = 'banned'")


def downgrade() -> None:
    op.drop_column("roles", "allow_login")
