"""add icon_media_id and is_recommended to pay_providers

Revision ID: 0008_pay_provider_meta
Revises: 0007_plugins_engine
Create Date: 2026-11-10 20:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_pay_provider_meta"
down_revision = "0007_plugins_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pay_providers",
        sa.Column(
            "icon_media_id",
            sa.Integer(),
            sa.ForeignKey("system_media.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "pay_providers",
        sa.Column(
            "is_recommended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pay_providers", "is_recommended")
    op.drop_column("pay_providers", "icon_media_id")
