"""add pending_order_config and auto_renew fields to user_services

Revision ID: 0007_service_lifecycle_fields
Revises: 0006_p2_indexes
Create Date: 2026-11-28 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_service_lifecycle_fields"
down_revision = "0006_p2_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_services", sa.Column("pending_order_config", sa.JSON(), nullable=True))
    op.add_column(
        "user_services",
        sa.Column("pending_apply_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_services",
        sa.Column("auto_renew", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user_services",
        sa.Column("auto_renew_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "user_services",
        sa.Column("auto_renew_last_error", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_services", "auto_renew_last_error")
    op.drop_column("user_services", "auto_renew_attempts")
    op.drop_column("user_services", "auto_renew")
    op.drop_column("user_services", "pending_apply_at")
    op.drop_column("user_services", "pending_order_config")
