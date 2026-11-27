"""add indexes on settings.prefix and digi_keys(service_id, id) WHERE is_used IS FALSE

Revision ID: 0006_p2_indexes
Revises: 0005_email_history_and_gdpr
Create Date: 2026-11-27 06:48:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_p2_indexes"
down_revision = "0005_email_history_and_gdpr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(op.f("ix_settings_prefix"), "settings", ["prefix"], unique=False)
    op.create_index(
        "ix_digi_keys_service_unused",
        "digi_keys",
        ["service_id", "id"],
        unique=False,
        postgresql_where=sa.text("is_used IS FALSE"),
    )


def downgrade() -> None:
    op.drop_index("ix_digi_keys_service_unused", table_name="digi_keys")
    op.drop_index(op.f("ix_settings_prefix"), table_name="settings")
