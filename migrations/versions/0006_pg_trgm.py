"""pg_trgm — расширение и GIN-индексы для fuzzy-поиска в admin-списках

Revision ID: 0006_pg_trgm
Revises: 0005_worker_jobs_owner
Create Date: 2026-07-22 00:00:00.000000

Добавляет расширение `pg_trgm` и триграммные GIN-индексы на текстовые поля,
по которым админка ищет "похожие" результаты (fallback, когда точный ILIKE
не находит ничего — см. utils/pagination.py::paginate_search и
IMPLEMENTATION_PLAN.md §0.5). Без индекса `similarity()`/`%` на этих таблицах
уйдёт в full scan при росте данных.
"""

from alembic import op


revision = '0006_pg_trgm'
down_revision = '0005_worker_jobs_owner'
branch_labels = None
depends_on = None

# (таблица, колонка) — те же поля, что используются как fuzzy_fields в
# соответствующих admin-роутах.
_TRGM_TARGETS = (
    ("accounts", "login"),
    ("accounts", "email"),
    ("services", "name"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for table, column in _TRGM_TARGETS:
        op.execute(
            f"CREATE INDEX ix_trgm_{table}_{column} ON {table} "
            f"USING GIN ({column} gin_trgm_ops)"
        )


def downgrade() -> None:
    for table, column in _TRGM_TARGETS:
        op.execute(f"DROP INDEX IF EXISTS ix_trgm_{table}_{column}")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
