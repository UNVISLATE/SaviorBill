"""user_services.delivery_attempts — счётчик попыток выдачи

Revision ID: 0010_delivery_attempts
Revises: 0009_email_case_insensitive
Create Date: 2026-08-01 00:00:00.000000

Провал Lua-выдачи после успешной оплаты оставлял услугу в `failed` навсегда:
деньги у продавца, услуги нет, автоматической компенсации не было (см.
AUDIT.md §3.1). Счётчик нужен, чтобы billing-loop повторил выдачу и, исчерпав
попытки, вернул сумму на внутренний баланс.
"""

from alembic import op
import sqlalchemy as sa


revision = '0010_delivery_attempts'
down_revision = '0009_email_case_insensitive'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_services",
        sa.Column(
            "delivery_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_user_services_failed_retry",
        "user_services",
        ["status", "delivery_attempts"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_services_failed_retry", "user_services")
    op.drop_column("user_services", "delivery_attempts")
