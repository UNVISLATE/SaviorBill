"""drop billing_tasks table (queue moved to Valkey)

Revision ID: 0005_drop_billing_tasks
Revises: 0004_pay_onescript
Create Date: 2026-07-01 14:00:00.000000

Планировщик хранит очередь исключительно в Valkey (UPDATE_PLAN.md, B7).
Таблица billing_tasks больше не нужна.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_drop_billing_tasks"
down_revision = "0004_pay_onescript"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_billing_tasks_status", table_name="billing_tasks")
    op.drop_index("ix_billing_tasks_run_at", table_name="billing_tasks")
    op.drop_index("ix_billing_tasks_ref_id", table_name="billing_tasks")
    op.drop_index("ix_billing_tasks_kind", table_name="billing_tasks")
    op.drop_table("billing_tasks")


def downgrade() -> None:
    op.create_table(
        "billing_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_billing_tasks_kind", "billing_tasks", ["kind"])
    op.create_index("ix_billing_tasks_ref_id", "billing_tasks", ["ref_id"])
    op.create_index("ix_billing_tasks_run_at", "billing_tasks", ["run_at"])
    op.create_index("ix_billing_tasks_status", "billing_tasks", ["status"])
