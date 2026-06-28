"""data layer: catalogs, pay_providers, settings; rename orders->user_services,
topups->payments; services.catalog_id/settings/image; owner role seed

Revision ID: 0003_data_layer
Revises: 0002_phase2
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_data_layer"
down_revision = "0002_phase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- каталоги услуг (иерархия) ---
    op.create_table(
        "svc_catalogs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("icon", sa.String(length=512), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["svc_catalogs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_svc_catalogs_slug", "svc_catalogs", ["slug"], unique=True)
    op.create_index("ix_svc_catalogs_parent_id", "svc_catalogs", ["parent_id"])

    # --- услуги: каталог, settings, изображение ---
    op.add_column(
        "services",
        sa.Column("catalog_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "services",
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "services",
        sa.Column("image", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_services_catalog_id", "services", ["catalog_id"])
    op.create_foreign_key(
        "fk_services_catalog_id",
        "services",
        "svc_catalogs",
        ["catalog_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- orders -> user_services (+payment_id) ---
    op.rename_table("orders", "user_services")
    op.add_column(
        "user_services",
        sa.Column("payment_id", sa.Integer(), nullable=True),
    )
    op.execute("ALTER INDEX ix_orders_account_id RENAME TO ix_user_services_account_id")
    op.execute("ALTER INDEX ix_orders_service_id RENAME TO ix_user_services_service_id")
    op.execute("ALTER INDEX ix_orders_status RENAME TO ix_user_services_status")
    op.create_index("ix_user_services_payment_id", "user_services", ["payment_id"])

    # --- topups -> payments (+target, +user_svc_id) ---
    op.rename_table("topups", "payments")
    op.add_column(
        "payments",
        sa.Column("target", sa.String(length=16), nullable=False, server_default="balance"),
    )
    op.add_column(
        "payments",
        sa.Column("user_svc_id", sa.Integer(), nullable=True),
    )
    op.execute("ALTER INDEX ix_topups_account_id RENAME TO ix_payments_account_id")
    op.execute("ALTER INDEX ix_topups_provider RENAME TO ix_payments_provider")
    op.execute("ALTER INDEX ix_topups_status RENAME TO ix_payments_status")
    op.execute("ALTER INDEX ix_topups_external_id RENAME TO ix_payments_external_id")
    op.create_index("ix_payments_user_svc_id", "payments", ["user_svc_id"])

    # --- платёжные провайдеры ---
    op.create_table(
        "pay_providers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("secrets_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("init_script_id", sa.Integer(), nullable=True),
        sa.Column("cb_script_id", sa.Integer(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["init_script_id"], ["lua_scripts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cb_script_id"], ["lua_scripts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pay_providers_slug", "pay_providers", ["slug"], unique=True)
    op.create_index("ix_pay_providers_init_script_id", "pay_providers", ["init_script_id"])
    op.create_index("ix_pay_providers_cb_script_id", "pay_providers", ["cb_script_id"])

    # --- key-value настройки ---
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- сид роли owner (все права) ---
    roles = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("title", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("perms", postgresql.JSONB),
    )
    op.bulk_insert(
        roles,
        [
            {
                "name": "owner",
                "title": "Владелец",
                "is_system": True,
                "perms": {"*": True},
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name = 'owner'")

    op.drop_table("settings")

    op.drop_index("ix_pay_providers_cb_script_id", table_name="pay_providers")
    op.drop_index("ix_pay_providers_init_script_id", table_name="pay_providers")
    op.drop_index("ix_pay_providers_slug", table_name="pay_providers")
    op.drop_table("pay_providers")

    # payments -> topups
    op.drop_index("ix_payments_user_svc_id", table_name="payments")
    op.drop_column("payments", "user_svc_id")
    op.drop_column("payments", "target")
    op.execute("ALTER INDEX ix_payments_external_id RENAME TO ix_topups_external_id")
    op.execute("ALTER INDEX ix_payments_status RENAME TO ix_topups_status")
    op.execute("ALTER INDEX ix_payments_provider RENAME TO ix_topups_provider")
    op.execute("ALTER INDEX ix_payments_account_id RENAME TO ix_topups_account_id")
    op.rename_table("payments", "topups")

    # user_services -> orders
    op.drop_index("ix_user_services_payment_id", table_name="user_services")
    op.drop_column("user_services", "payment_id")
    op.execute("ALTER INDEX ix_user_services_status RENAME TO ix_orders_status")
    op.execute("ALTER INDEX ix_user_services_service_id RENAME TO ix_orders_service_id")
    op.execute("ALTER INDEX ix_user_services_account_id RENAME TO ix_orders_account_id")
    op.rename_table("user_services", "orders")

    # services: убрать catalog_id/settings/image
    op.drop_constraint("fk_services_catalog_id", "services", type_="foreignkey")
    op.drop_index("ix_services_catalog_id", table_name="services")
    op.drop_column("services", "image")
    op.drop_column("services", "settings")
    op.drop_column("services", "catalog_id")

    op.drop_index("ix_svc_catalogs_parent_id", table_name="svc_catalogs")
    op.drop_index("ix_svc_catalogs_slug", table_name="svc_catalogs")
    op.drop_table("svc_catalogs")
