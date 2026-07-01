"""lifecycle fields + billing_tasks queue

Revision ID: 0002_lifecycle_queue
Revises: 0001_init
Create Date: 2026-07-01 04:40:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_lifecycle_queue"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- services: поддерживаемые действия + срок действия ---
    op.add_column(
        "services",
        sa.Column("actions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column("services", sa.Column("duration", sa.Integer(), nullable=True))

    # --- user_services: состояние ЖЦ, истечение, снимок действий ---
    op.add_column(
        "user_services",
        sa.Column(
            "state",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
    )
    op.add_column(
        "user_services",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("user_services", sa.Column("duration", sa.Integer(), nullable=True))
    op.add_column(
        "user_services",
        sa.Column("actions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.create_index("ix_user_services_state", "user_services", ["state"], unique=False)
    op.create_index(
        "ix_user_services_expires_at", "user_services", ["expires_at"], unique=False
    )

    # --- billing_tasks: очередь отложенных задач billing-loop ---
    op.create_table(
        "billing_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
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
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_tasks_kind", "billing_tasks", ["kind"])
    op.create_index("ix_billing_tasks_ref_id", "billing_tasks", ["ref_id"])
    op.create_index("ix_billing_tasks_run_at", "billing_tasks", ["run_at"])
    op.create_index("ix_billing_tasks_status", "billing_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_billing_tasks_status", table_name="billing_tasks")
    op.drop_index("ix_billing_tasks_run_at", table_name="billing_tasks")
    op.drop_index("ix_billing_tasks_ref_id", table_name="billing_tasks")
    op.drop_index("ix_billing_tasks_kind", table_name="billing_tasks")
    op.drop_table("billing_tasks")

    op.drop_index("ix_user_services_expires_at", table_name="user_services")
    op.drop_index("ix_user_services_state", table_name="user_services")
    op.drop_column("user_services", "actions")
    op.drop_column("user_services", "duration")
    op.drop_column("user_services", "expires_at")
    op.drop_column("user_services", "state")

    op.drop_column("services", "duration")
    op.drop_column("services", "actions")
