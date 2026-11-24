"""scheduled_tasks outbox table, notify trigger, and initial backfill

Revision ID: 0002_scheduled_tasks
Revises: 0001_initial
Create Date: 2026-11-24 21:55:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_scheduled_tasks"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dedup_key", sa.String(length=128), nullable=True),
        sa.Column("task_kind", sa.String(length=32), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_scheduled_tasks_active_dedup
            ON scheduled_tasks (dedup_key)
            WHERE dedup_key IS NOT NULL AND status IN ('pending', 'dispatched', 'processing');
        """
    )
    op.execute(
        """
        CREATE INDEX ix_scheduled_tasks_due
            ON scheduled_tasks (status, run_at)
            WHERE status IN ('pending', 'dispatched');
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_scheduled_task() RETURNS trigger AS $$
        BEGIN
            IF NEW.status = 'pending' AND NEW.run_at <= (now() + interval '1 hour') THEN
                PERFORM pg_notify(
                    'sb_sched_events',
                    json_build_object(
                        'id', NEW.id,
                        'run_at', extract(epoch from NEW.run_at),
                        'version', NEW.version
                    )::text
                );
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_scheduled_tasks_notify
        AFTER INSERT OR UPDATE OF run_at, status ON scheduled_tasks
        FOR EACH ROW EXECUTE FUNCTION notify_scheduled_task();
        """
    )

    # Однократный перенос активных задач из существующих таблиц.
    op.execute(
        """
        INSERT INTO scheduled_tasks (dedup_key, task_kind, ref_id, run_at, status)
        SELECT 'svc:' || id, 'svc_expire', id, expires_at, 'pending'
        FROM user_services
        WHERE status = 'active' AND expires_at IS NOT NULL
        ON CONFLICT DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO scheduled_tasks (dedup_key, task_kind, ref_id, run_at, status)
        SELECT 'pay:' || id, 'pay_recheck', id, created_at + interval '15 minutes', 'pending'
        FROM payments
        WHERE status = 'pending'
        ON CONFLICT DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO scheduled_tasks (dedup_key, task_kind, ref_id, run_at, status)
        SELECT 'dlv:' || id, 'dlv_retry', id, now(), 'pending'
        FROM user_services
        WHERE status = 'failed'
          AND (private_data IS NULL OR NOT (private_data::jsonb ? 'delivery_credit'))
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_scheduled_tasks_notify ON scheduled_tasks;")
    op.execute("DROP FUNCTION IF EXISTS notify_scheduled_task();")
    op.drop_index("ix_scheduled_tasks_due", table_name="scheduled_tasks")
    op.drop_index("uq_scheduled_tasks_active_dedup", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
