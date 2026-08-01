"""accounts: TOTP-двухфакторка

Revision ID: 0013_totp
Revises: 0012_payment_base_amount
Create Date: 2026-08-02 00:00:00.000000

Владелец и администраторы имели неограниченный доступ по одному лишь паролю
(см. AUDIT.md §1.5 LOW-1). Секрет TOTP хранится зашифрованным, коды
восстановления — только в виде хэшей.
"""

from alembic import op
import sqlalchemy as sa


revision = '0013_totp'
down_revision = '0012_payment_base_amount'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("totp_secret", sa.String(512), nullable=True))
    op.add_column(
        "accounts",
        sa.Column(
            "totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "totp_recovery",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "totp_recovery")
    op.drop_column("accounts", "totp_enabled")
    op.drop_column("accounts", "totp_secret")
