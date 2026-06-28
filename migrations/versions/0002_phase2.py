"""phase2: balances, lua_scripts, services, digi_keys, orders, topups, promocodes, promo_uses + role seed

Revision ID: 0002_phase2
Revises: 0001_init
Create Date: 2026-06-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_phase2"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- accounts: денежные балансы (Decimal) ---
    op.add_column(
        "accounts",
        sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "accounts",
        sa.Column("bonus_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )

    # --- карта Lua-скриптов ---
    op.create_table(
        "lua_scripts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="service"),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lua_scripts_slug", "lua_scripts", ["slug"], unique=True)

    # --- услуги ---
    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("delivery", sa.String(length=8), nullable=False, server_default="key"),
        sa.Column("lua_script_id", sa.Integer(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["lua_script_id"], ["lua_scripts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_services_slug", "services", ["slug"], unique=True)
    op.create_index("ix_services_lua_script_id", "services", ["lua_script_id"])

    # --- пул цифровых ключей ---
    op.create_table(
        "digi_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_digi_keys_service_id", "digi_keys", ["service_id"])
    op.create_index("ix_digi_keys_is_used", "digi_keys", ["is_used"])

    # --- заказы (товары пользователя) ---
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="initiated"),
        sa.Column("price", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("discount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("public_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("private_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("digikey_id", sa.Integer(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_service_id", "orders", ["service_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # --- пополнения ---
    op.create_table(
        "topups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("public_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("private_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_topups_account_id", "topups", ["account_id"])
    op.create_index("ix_topups_provider", "topups", ["provider"])
    op.create_index("ix_topups_status", "topups", ["status"])
    op.create_index("ix_topups_external_id", "topups", ["external_id"])

    # --- промокоды ---
    op.create_table(
        "promocodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("discount_type", sa.String(length=8), nullable=False, server_default="percent"),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("per_user", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_promocodes_code", "promocodes", ["code"], unique=True)

    # --- применения промокодов ---
    op.create_table(
        "promo_uses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("promocode_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["promocode_id"], ["promocodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_promo_uses_promocode_id", "promo_uses", ["promocode_id"])
    op.create_index("ix_promo_uses_account_id", "promo_uses", ["account_id"])

    # --- сид системных ролей ---
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
                "name": "admin",
                "title": "Администратор",
                "is_system": True,
                "perms": {"*": True},
            },
            {
                "name": "manager",
                "title": "Менеджер",
                "is_system": True,
                "perms": {
                    "users": {"read": True, "edit": True},
                    "orders": {"read": True},
                    "topups": {"read": True},
                    "scripts": {"read": True, "edit": True},
                },
            },
            {
                "name": "support",
                "title": "Поддержка",
                "is_system": True,
                "perms": {
                    "users": {"read": True},
                    "orders": {"read": True},
                    "topups": {"read": True},
                },
            },
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name IN ('admin', 'manager', 'support')")

    op.drop_index("ix_promo_uses_account_id", table_name="promo_uses")
    op.drop_index("ix_promo_uses_promocode_id", table_name="promo_uses")
    op.drop_table("promo_uses")

    op.drop_index("ix_promocodes_code", table_name="promocodes")
    op.drop_table("promocodes")

    op.drop_index("ix_topups_external_id", table_name="topups")
    op.drop_index("ix_topups_status", table_name="topups")
    op.drop_index("ix_topups_provider", table_name="topups")
    op.drop_index("ix_topups_account_id", table_name="topups")
    op.drop_table("topups")

    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_service_id", table_name="orders")
    op.drop_index("ix_orders_account_id", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_digi_keys_is_used", table_name="digi_keys")
    op.drop_index("ix_digi_keys_service_id", table_name="digi_keys")
    op.drop_table("digi_keys")

    op.drop_index("ix_services_lua_script_id", table_name="services")
    op.drop_index("ix_services_slug", table_name="services")
    op.drop_table("services")

    op.drop_index("ix_lua_scripts_slug", table_name="lua_scripts")
    op.drop_table("lua_scripts")

    op.drop_column("accounts", "bonus_balance")
    op.drop_column("accounts", "balance")
