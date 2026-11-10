"""add referral_bonus_earned to accounts

Revision ID: 0009_referral_bonus_earned
Revises: 0008_pay_provider_meta
Create Date: 2026-11-10 22:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_referral_bonus_earned"
down_revision = "0008_pay_provider_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "referral_bonus_earned",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "referral_bonus_earned")
