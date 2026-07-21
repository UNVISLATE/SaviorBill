"""worker_jobs.owner_id — денормализованный владелец джобы

Revision ID: 0005_worker_jobs_owner
Revises: 0004_settings_prefix
Create Date: 2026-07-21 00:00:00.000000

``system_media`` для конкретного токена создаётся только консьюмером
результата конвертации (``services/media_results.py``), то есть ПОСЛЕ того,
как джоба уже была queued/processing в ``worker_jobs`` — джойн "джобы
владельца" на ``system_media`` без денормализации всегда возвращал пустой
список для ещё не готовых файлов (баг: "мои активные джобы" не подхватывали
только что запущенные загрузки). owner_id теперь пишется в саму джобу сразу
при создании — воркер знает владельца уже из исходной задачи в очереди.
"""

from alembic import op
import sqlalchemy as sa


revision = '0005_worker_jobs_owner'
down_revision = '0004_settings_prefix'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('worker_jobs', sa.Column('owner_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_worker_jobs_owner', 'worker_jobs', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_worker_jobs_owner', table_name='worker_jobs')
    op.drop_column('worker_jobs', 'owner_id')
