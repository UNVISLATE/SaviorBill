"""add custom_public, custom_private and plugin_migrations

Revision ID: 0007_plugins_engine
Revises: 0006_create_app_tokens
Create Date: 2026-11-09 04:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0007_plugins_engine'
down_revision = '0006_create_app_tokens'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. accounts
    op.add_column(
        'accounts',
        sa.Column(
            'custom_public',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        'accounts',
        sa.Column(
            'custom_private',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # 2. services
    op.add_column(
        'services',
        sa.Column(
            'custom_public',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        'services',
        sa.Column(
            'custom_private',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # 3. user_services
    op.add_column(
        'user_services',
        sa.Column(
            'custom_public',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        'user_services',
        sa.Column(
            'custom_private',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # 4. plugin_migrations
    op.create_table(
        'plugin_migrations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('plugin_slug', sa.String(length=64), nullable=False),
        sa.Column('migration_file', sa.String(length=255), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('plugin_slug', 'migration_file', name='uq_plugin_migrations_slug_file'),
    )


def downgrade() -> None:
    op.drop_table('plugin_migrations')
    op.drop_column('user_services', 'custom_private')
    op.drop_column('user_services', 'custom_public')
    op.drop_column('services', 'custom_private')
    op.drop_column('services', 'custom_public')
    op.drop_column('accounts', 'custom_private')
    op.drop_column('accounts', 'custom_public')
