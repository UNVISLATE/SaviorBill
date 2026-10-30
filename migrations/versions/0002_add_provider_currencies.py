"""add provider currencies

Revision ID: 0002_add_provider_currencies
Revises: 0001_initial
Create Date: 2026-10-25 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0002_add_provider_currencies'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'pay_providers',
        sa.Column('currencies', sa.JSON(), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('pay_providers', 'currencies')
