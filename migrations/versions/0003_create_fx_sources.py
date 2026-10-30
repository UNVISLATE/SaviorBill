"""create fx_sources table

Revision ID: 0003_create_fx_sources
Revises: 0002_add_provider_currencies
Create Date: 2026-10-25 15:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0003_create_fx_sources'
down_revision = '0002_add_provider_currencies'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fx_sources',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=128), server_default='', nullable=False),
        sa.Column('priority', sa.Integer(), server_default='0', nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=True),
        sa.Column('api_key_enc', sa.Text(), server_default='', nullable=False),
        sa.Column('script_id', sa.Integer(), nullable=True),
        sa.Column('lua_slug', sa.String(length=64), nullable=True),
        sa.Column('rates', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('last_rates', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['script_id'], ['lua_scripts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fx_sources_priority'), 'fx_sources', ['priority'], unique=False)
    op.create_index(op.f('ix_fx_sources_enabled'), 'fx_sources', ['enabled'], unique=False)
    op.create_index(op.f('ix_fx_sources_script_id'), 'fx_sources', ['script_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fx_sources_script_id'), table_name='fx_sources')
    op.drop_index(op.f('ix_fx_sources_enabled'), table_name='fx_sources')
    op.drop_index(op.f('ix_fx_sources_priority'), table_name='fx_sources')
    op.drop_table('fx_sources')
