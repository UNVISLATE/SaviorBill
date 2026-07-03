"""media variants column

Добавляет ``system_media.variants`` (JSON): набор вариантов файла
(main/thumb/preview/preview_thumb), которые генерирует mediaworker.

Revision ID: 0010_media_variants
Revises: 0009_script_guard_oauth
Create Date: 2024-01-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_media_variants"
down_revision = "0009_script_guard_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_media",
        sa.Column(
            "variants",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_media", "variants")
