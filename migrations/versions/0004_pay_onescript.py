"""payment provider single script + lua_scripts.actions

Revision ID: 0004_pay_onescript
Revises: 0003_dedup_roles_usvc
Create Date: 2026-07-01 13:00:00.000000

Единый action-driven скрипт платёжного провайдера (UPDATE_PLAN.md, B5):
  * lua_scripts.actions — заявленные поддерживаемые действия скрипта.
  * pay_providers: init_script_id + cb_script_id → единый script_id.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_pay_onescript"
down_revision = "0003_dedup_roles_usvc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- lua_scripts.actions ---
    op.add_column(
        "lua_scripts",
        sa.Column(
            "actions",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )

    # --- pay_providers: слить два скрипта в один ---
    op.add_column("pay_providers", sa.Column("script_id", sa.Integer(), nullable=True))
    # Переносим init_script_id (приоритет) либо cb_script_id в единый script_id.
    op.execute(
        "UPDATE pay_providers " "SET script_id = COALESCE(init_script_id, cb_script_id)"
    )
    op.create_index(
        op.f("ix_pay_providers_script_id"),
        "pay_providers",
        ["script_id"],
    )
    op.create_foreign_key(
        "fk_pay_providers_script_id",
        "pay_providers",
        "lua_scripts",
        ["script_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_index(op.f("ix_pay_providers_init_script_id"), table_name="pay_providers")
    op.drop_index(op.f("ix_pay_providers_cb_script_id"), table_name="pay_providers")
    op.drop_column("pay_providers", "init_script_id")
    op.drop_column("pay_providers", "cb_script_id")


def downgrade() -> None:
    op.add_column(
        "pay_providers", sa.Column("cb_script_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "pay_providers", sa.Column("init_script_id", sa.Integer(), nullable=True)
    )
    op.execute("UPDATE pay_providers SET init_script_id = script_id")
    op.create_index(
        op.f("ix_pay_providers_cb_script_id"), "pay_providers", ["cb_script_id"]
    )
    op.create_index(
        op.f("ix_pay_providers_init_script_id"), "pay_providers", ["init_script_id"]
    )
    op.create_foreign_key(
        None,
        "pay_providers",
        "lua_scripts",
        ["init_script_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        None,
        "pay_providers",
        "lua_scripts",
        ["cb_script_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_pay_providers_script_id", "pay_providers", type_="foreignkey"
    )
    op.drop_index(op.f("ix_pay_providers_script_id"), table_name="pay_providers")
    op.drop_column("pay_providers", "script_id")
    op.drop_column("lua_scripts", "actions")
