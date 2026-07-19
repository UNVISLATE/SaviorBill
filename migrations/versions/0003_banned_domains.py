"""banned_email_domains — запрещённые для регистрации email-домены

Revision ID: 0003_banned_domains
Revises: 0002_worker_jobs
Create Date: 2026-07-19 00:00:00.000000

Отдельная таблица вместо settings-ключа со списком — индексированный точный
поиск по домену на каждую регистрацию (см. models/banned_email_domains.py).
"""

from alembic import op
import sqlalchemy as sa


revision = '0003_banned_domains'
down_revision = '0002_worker_jobs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'banned_email_domains',
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('domain'),
    )


def downgrade() -> None:
    op.drop_table('banned_email_domains')
