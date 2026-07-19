"""worker_jobs + worker_job_events — единая state machine статусов задач воркеров

Revision ID: 0002_worker_jobs
Revises: 0001_init
Create Date: 2026-07-20 00:00:00.000000

Authoritative источник статуса медиа-конвейера (convert/preview_add/
thumb_replace): `worker_jobs.state` (queued/processing/retrying/ready/failed/
stale/cancelled) + append-only история переходов `worker_job_events`.
Valkey (`media:status:*`) остаётся быстрым кэшем, не единственным источником.
"""

from alembic import op
import sqlalchemy as sa


revision = '0002_worker_jobs'
down_revision = '0001_init'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'worker_jobs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('op', sa.String(length=32), nullable=False),
        sa.Column('subject_key', sa.String(length=64), nullable=False),
        sa.Column('state', sa.String(length=16), server_default='queued', nullable=False),
        sa.Column('attempt', sa.Integer(), server_default='1', nullable=False),
        sa.Column('worker_id', sa.String(length=128), nullable=True),
        sa.Column('error', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_worker_jobs_kind_subject', 'worker_jobs', ['kind', 'subject_key'])
    op.create_index('ix_worker_jobs_state', 'worker_jobs', ['state'])

    op.create_table(
        'worker_job_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(length=16), nullable=False),
        sa.Column('data', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['worker_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_worker_job_events_job_created', 'worker_job_events', ['job_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_worker_job_events_job_created', table_name='worker_job_events')
    op.drop_table('worker_job_events')
    op.drop_index('ix_worker_jobs_state', table_name='worker_jobs')
    op.drop_index('ix_worker_jobs_kind_subject', table_name='worker_jobs')
    op.drop_table('worker_jobs')
