"""add services 2.0 pricing config and order config

Revision ID: 0005_services_2_0_pricing
Revises: 0004_add_provider_fees
Create Date: 2026-10-30 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0005_services_2_0_pricing'
down_revision = '0004_add_provider_fees'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'services',
        sa.Column('price_type', sa.String(length=16), server_default='fixed', nullable=False),
    )
    op.add_column(
        'services',
        sa.Column('pricing_config', sa.JSON(), server_default='{}', nullable=False),
    )
    op.add_column(
        'user_services',
        sa.Column('order_config', sa.JSON(), server_default='{}', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('user_services', 'order_config')
    op.drop_column('services', 'pricing_config')
    op.drop_column('services', 'price_type')
