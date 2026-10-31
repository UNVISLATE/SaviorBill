"""create app_tokens table

Revision ID: 0006_create_app_tokens
Revises: 0005_services_2_0_pricing
Create Date: 2026-10-31 16:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0006_create_app_tokens'
down_revision = '0005_services_2_0_pricing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'app_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('token_prefix', sa.String(length=24), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('ip_allowlist', sa.JSON(), nullable=True),
        sa.Column('created_by_account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_ip', sa.String(length=64), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by_account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_app_tokens_token_hash', 'app_tokens', ['token_hash'], unique=True)
    op.create_index('ix_app_tokens_created_by', 'app_tokens', ['created_by_account_id'])


def downgrade() -> None:
    op.drop_index('ix_app_tokens_created_by', table_name='app_tokens')
    op.drop_index('ix_app_tokens_token_hash', table_name='app_tokens')
    op.drop_table('app_tokens')
