"""role.key + drop user bool duplicates + merge usvc status/state + product fields

Revision ID: 0003_dedup_roles_usvc
Revises: 0002_lifecycle_queue
Create Date: 2026-07-01 12:00:00.000000

Дедупликация полей-дубликатов (UPDATE_PLAN.md):
  * roles.key — стабильный ключ базовой роли (owner/admin/user/guest/banned…).
  * accounts: убраны is_active/is_verified (производные от роли).
  * user_services: слиты status+state в единый status; убран params;
    добавлены product_key/product_kind.
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_dedup_roles_usvc"
down_revision = "0002_lifecycle_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- roles: стабильный ключ базовой роли ---
    op.add_column("roles", sa.Column("key", sa.String(length=32), nullable=True))
    op.create_index("ix_roles_key", "roles", ["key"], unique=True)
    # Бэкфилл ключей системных ролей по имени (дефолтные имена == ключам).
    op.execute("UPDATE roles SET key = name WHERE is_system = true AND key IS NULL")

    # --- accounts: is_active/is_verified теперь производные от роли ---
    # Перенос данных: неактивные -> роль banned (по ключу/имени).
    op.execute(
        "UPDATE accounts SET role_id = ("
        "  SELECT id FROM roles WHERE key = 'banned' OR name = 'banned' LIMIT 1"
        ") WHERE is_active = false"
    )
    op.drop_column("accounts", "is_active")
    op.drop_column("accounts", "is_verified")

    # --- user_services: единый status (было status + state) ---
    # Смапить прежний статус доставки в единый статус ЖЦ.
    op.execute("UPDATE user_services SET status = 'active' WHERE status = 'delivered'")
    op.execute("UPDATE user_services SET status = 'pending' WHERE status = 'initiated'")
    op.execute(
        "UPDATE user_services SET status = 'pending' WHERE status = 'processing'"
    )
    # Активные с нетривиальным состоянием ЖЦ — взять состояние из state.
    op.execute(
        "UPDATE user_services SET status = state "
        "WHERE status = 'active' AND state IN ('frozen','stopped','expired')"
    )
    op.drop_index("ix_user_services_state", table_name="user_services")
    op.drop_column("user_services", "state")
    op.drop_column("user_services", "params")
    op.add_column(
        "user_services",
        sa.Column("product_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_services",
        sa.Column("product_kind", sa.String(length=32), nullable=True),
    )
    op.alter_column(
        "user_services",
        "status",
        server_default="pending",
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "user_services",
        "status",
        server_default=None,
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )
    op.drop_column("user_services", "product_kind")
    op.drop_column("user_services", "product_key")
    op.add_column(
        "user_services",
        sa.Column("params", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "user_services",
        sa.Column(
            "state", sa.String(length=16), server_default="active", nullable=False
        ),
    )
    op.create_index("ix_user_services_state", "user_services", ["state"], unique=False)

    op.add_column(
        "accounts",
        sa.Column(
            "is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )

    op.drop_index("ix_roles_key", table_name="roles")
    op.drop_column("roles", "key")
