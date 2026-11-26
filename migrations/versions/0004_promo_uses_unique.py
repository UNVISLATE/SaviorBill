"""unique constraint on promo_uses (promocode_id, account_id)

Revision ID: 0004_promo_uses_unique
Revises: 0003_lua_artifacts_and_plugins
Create Date: 2026-11-27 00:20:00.000000
"""

from alembic import op


revision = "0004_promo_uses_unique"
down_revision = "0003_lua_artifacts_and_plugins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_promo_uses_code_account",
        "promo_uses",
        ["promocode_id", "account_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_promo_uses_code_account",
        "promo_uses",
        type_="unique",
    )
