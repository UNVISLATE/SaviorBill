"""referral program: accounts.ref_code + accounts.referred_by

Revision ID: 0006_referral
Revises: 0005_drop_billing_tasks
Create Date: 2026-07-01 15:00:00.000000

Реферальная система (UPDATE_PLAN.md, B8): собственный реферальный код аккаунта
и ссылка на пригласившего пользователя.
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_referral"
down_revision = "0005_drop_billing_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts", sa.Column("ref_code", sa.String(length=16), nullable=True)
    )
    op.add_column("accounts", sa.Column("referred_by", sa.Integer(), nullable=True))
    op.create_index("ix_accounts_ref_code", "accounts", ["ref_code"], unique=True)
    op.create_index("ix_accounts_referred_by", "accounts", ["referred_by"])
    op.create_foreign_key(
        "fk_accounts_referred_by",
        "accounts",
        "accounts",
        ["referred_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_accounts_referred_by", "accounts", type_="foreignkey")
    op.drop_index("ix_accounts_referred_by", table_name="accounts")
    op.drop_index("ix_accounts_ref_code", table_name="accounts")
    op.drop_column("accounts", "referred_by")
    op.drop_column("accounts", "ref_code")
