"""payments: сумма в базовой валюте и применённый курс

Revision ID: 0012_payment_base_amount
Revises: 0011_role_is_protected
Create Date: 2026-08-02 00:00:00.000000

У платежа была валюта, а у баланса аккаунта — нет, поэтому пополнение в USD
молча прибавлялось к рублёвому балансу (см. AUDIT.md §2.3). Теперь зачисление
конвертируется в базовую валюту инстанса, а результат конвертации хранится
рядом с платежом: возврат должен списывать ровно ту сумму, которая была
зачислена, а не пересчитывать её по сегодняшнему курсу.
"""

from alembic import op
import sqlalchemy as sa


revision = '0012_payment_base_amount'
down_revision = '0011_role_is_protected'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments", sa.Column("base_amount", sa.Numeric(18, 2), nullable=True)
    )
    op.add_column(
        "payments", sa.Column("base_currency", sa.String(8), nullable=True)
    )
    op.add_column("payments", sa.Column("fx_rate", sa.Numeric(24, 10), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "fx_rate")
    op.drop_column("payments", "base_currency")
    op.drop_column("payments", "base_amount")
