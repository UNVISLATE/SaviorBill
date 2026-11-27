"""account_email_history table and accounts.email_verified_at / last_security_change_at

Revision ID: 0005_email_history_and_gdpr
Revises: 0004_promo_uses_unique
Create Date: 2026-11-27 06:42:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_email_history_and_gdpr"
down_revision = "0004_promo_uses_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column("last_security_change_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "account_email_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_initial_verified",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default="profile",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_email_history_account_id"),
        "account_email_history",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_email_history_email"),
        "account_email_history",
        ["email"],
        unique=False,
    )
    op.create_index(
        "ix_account_email_history_acc_created",
        "account_email_history",
        ["account_id", "created_at"],
        unique=False,
    )

    # Backfill для существующих аккаунтов с email.
    op.execute(
        """
        UPDATE accounts a
        SET email_verified_at = a.created_at
        FROM roles r
        WHERE a.role_id = r.id
          AND a.email IS NOT NULL
          AND r.key NOT IN ('guest', 'banned');
        """
    )
    op.execute(
        """
        INSERT INTO account_email_history (created_at, account_id, email, verified_at, is_initial_verified, source)
        SELECT a.created_at,
               a.id,
               lower(trim(a.email)),
               a.email_verified_at,
               (a.email_verified_at IS NOT NULL),
               'backfill'
        FROM accounts a
        WHERE a.email IS NOT NULL AND trim(a.email) <> '';
        """
    )


def downgrade() -> None:
    op.drop_index("ix_account_email_history_acc_created", table_name="account_email_history")
    op.drop_index(op.f("ix_account_email_history_email"), table_name="account_email_history")
    op.drop_index(op.f("ix_account_email_history_account_id"), table_name="account_email_history")
    op.drop_table("account_email_history")
    op.drop_column("accounts", "last_security_change_at")
    op.drop_column("accounts", "email_verified_at")
