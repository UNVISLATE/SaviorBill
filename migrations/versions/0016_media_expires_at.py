"""system_media: expires_at (для авто-GC неподтверждённых кандидатов аватарки)

Revision ID: 0016_media_expires_at
Revises: 0015_media_quota_v2
Create Date: 2026-08-03 00:00:00.000000

Проблема (см. AUDIT.md §4, "квота съедается брошенными загрузками"): каждая
попытка подобрать аватар (пользователь загружает несколько фото, прежде чем
выбрать одно) навсегда занимает слот в ``user.media.limit`` — до этой миграции
единственная чистка "осиротевших" медиа была ручной (`POST /admin/media/cleanup`).

``expires_at`` — дедлайн подтверждения для кандидатов (``tag=avatar``),
проставляется консьюмером результатов конвертации (``services/media_results.py``)
и снимается при реальном подтверждении (``PUT /me/avatar``). Обрабатывается
фоновым ``BillingLoop`` через тот же общий ZSET, что и остальные задачи биллинга.
"""

from alembic import op
import sqlalchemy as sa


revision = '0016_media_expires_at'
down_revision = '0015_media_quota_v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_media",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_system_media_expires_at", "system_media", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_system_media_expires_at", table_name="system_media")
    op.drop_column("system_media", "expires_at")
