"""add provider fee settings

Revision ID: 0004_add_provider_fees
Revises: 0003_create_fx_sources
Create Date: 2026-10-25 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0004_add_provider_fees'
down_revision = '0003_create_fx_sources'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'pay_providers',
        sa.Column('fee_enabled', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'pay_providers',
        sa.Column('fee_percent', sa.Numeric(precision=5, scale=2), server_default='0.00', nullable=False),
    )
    op.add_column(
        'pay_providers',
        sa.Column('add_fee_to_amount', sa.Boolean(), server_default='true', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('pay_providers', 'add_fee_to_amount')
    op.drop_column('pay_providers', 'fee_percent')
    op.drop_column('pay_providers', 'fee_enabled')
